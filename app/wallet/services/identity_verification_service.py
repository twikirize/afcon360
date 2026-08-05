"""
Identity verification service for sensitive wallet actions.

Provides re-verification workflows for high-risk operations such as
password changes, email/phone updates, large transactions, and wallet activation.
"""

from typing import Dict, Any, List, Optional
from flask import current_app, session
from flask_login import current_user
from datetime import datetime, timezone, timedelta

from app.extensions import db
from app.identity.models.user import User
from app.wallet.models.transaction import TransactionModel


class IdentityVerificationService:
    """
    Service for managing identity verification during sensitive actions.
    
    Requires users to re-verify their identity through multiple factors
    before performing high-risk operations.
    """

    VERIFICATION_METHODS = {
        'change_email': ['current_password', 'mfa'],
        'change_phone': ['current_password', 'mfa'],
        'change_password': ['current_password', 'mfa'],
        'wallet_activation': ['email_otp', 'phone_otp'],
        'large_withdrawal': ['mfa', 'transaction_pin'],
        'large_transfer': ['mfa', 'transaction_pin'],
        'close_account': ['mfa', 'security_question'],
        'change_pin': ['current_password', 'mfa'],
    }

    SESSION_PREFIX = 'identity_verification_'
    SESSION_TTL = timedelta(minutes=10)

    @classmethod
    def get_required_methods(cls, action_type: str) -> List[str]:
        """Get required verification methods for an action."""
        return cls.VERIFICATION_METHODS.get(action_type, ['mfa'])

    @classmethod
    def is_verified(cls, user_id: int, action_type: str) -> bool:
        """Check if user has completed identity verification for action."""
        session_key = f"{cls.SESSION_PREFIX}{action_type}_{user_id}"
        verified_data = session.get(session_key)
        
        if not verified_data:
            return False
        
        # Check TTL
        verified_at = verified_data.get('verified_at')
        if not verified_at:
            return False
        
        if datetime.now(timezone.utc) - verified_at > cls.SESSION_TTL:
            session.pop(session_key, None)
            return False
        
        return True

    @classmethod
    def mark_verified(cls, user_id: int, action_type: str, methods_used: List[str]) -> None:
        """Mark identity verification as complete for action."""
        session_key = f"{cls.SESSION_PREFIX}{action_type}_{user_id}"
        session[session_key] = {
            'user_id': user_id,
            'action': action_type,
            'methods_used': methods_used,
            'verified_at': datetime.now(timezone.utc).isoformat()
        }

    @classmethod
    def clear_verification(cls, user_id: int, action_type: str) -> None:
        """Clear identity verification for action."""
        session_key = f"{cls.SESSION_PREFIX}{action_type}_{user_id}"
        session.pop(session_key, None)

    @classmethod
    def verify_current_password(cls, user_id: int, password: str) -> Dict[str, Any]:
        """Verify current password."""
        user = db.session.get(User, user_id)
        if not user:
            return {'success': False, 'reason': 'User not found'}
        
        if not user.check_password(password):
            return {'success': False, 'reason': 'Incorrect password'}
        
        return {'success': True, 'method': 'current_password'}

    @classmethod
    def verify_mfa(cls, user_id: int, mfa_code: str) -> Dict[str, Any]:
        """Verify MFA code."""
        user = db.session.get(User, user_id)
        if not user:
            return {'success': False, 'reason': 'User not found'}
        
        if not user.mfa_enabled:
            return {'success': False, 'reason': 'MFA not enabled'}
        
        # Verify TOTP code
        from app.auth.mfa_service import MFAService
        mfa_service = MFAService()
        if not mfa_service.verify_totp(user.mfa_secret, mfa_code):
            return {'success': False, 'reason': 'Invalid MFA code'}
        
        return {'success': True, 'method': 'mfa'}

    @classmethod
    def verify_transaction_pin(cls, user_id: int, pin: str) -> Dict[str, Any]:
        """Verify transaction PIN."""
        user = db.session.get(User, user_id)
        if not user:
            return {'success': False, 'reason': 'User not found'}
        
        if not user.transaction_pin_hash:
            return {'success': False, 'reason': 'Transaction PIN not set'}
        
        if not user.verify_transaction_pin(pin):
            return {'success': False, 'reason': 'Invalid transaction PIN'}
        
        return {'success': True, 'method': 'transaction_pin'}

    @classmethod
    def verify_security_question(cls, user_id: int, answer: str) -> Dict[str, Any]:
        """Verify security question answer."""
        user = db.session.get(User, user_id)
        if not user:
            return {'success': False, 'reason': 'User not found'}
        
        if not user.security_answer_hash:
            return {'success': False, 'reason': 'Security question not set'}
        
        from werkzeug.security import check_password_hash
        if not check_password_hash(user.security_answer_hash, answer.strip().lower()):
            return {'success': False, 'reason': 'Incorrect security answer'}
        
        return {'success': True, 'method': 'security_question'}

    @classmethod
    def verify_email_otp(cls, user_id: int, otp_code: str) -> Dict[str, Any]:
        """Verify email OTP."""
        user = db.session.get(User, user_id)
        if not user:
            return {'success': False, 'reason': 'User not found'}
        
        from app.auth.otp_service import OTPService
        otp_service = OTPService()
        if not otp_service.verify_email_otp(user.email, otp_code):
            return {'success': False, 'reason': 'Invalid or expired email OTP'}
        
        return {'success': True, 'method': 'email_otp'}

    @classmethod
    def verify_phone_otp(cls, user_id: int, otp_code: str) -> Dict[str, Any]:
        """Verify phone OTP."""
        user = db.session.get(User, user_id)
        if not user:
            return {'success': False, 'reason': 'User not found'}
        
        if not user.phone:
            return {'success': False, 'reason': 'Phone number not set'}
        
        from app.auth.otp_service import OTPService
        otp_service = OTPService()
        if not otp_service.verify_sms_otp(user.phone, otp_code):
            return {'success': False, 'reason': 'Invalid or expired phone OTP'}
        
        return {'success': True, 'method': 'phone_otp'}

    @classmethod
    def require_verification(cls, action_type: str, user_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Check if verification is required for an action.
        
        Returns:
            Dict with 'required' (bool), 'methods' (list), and optionally
            'missing_methods' if required but not yet completed.
        """
        if user_id is None:
            if not current_user or not current_user.is_authenticated:
                return {
                    'required': True,
                    'methods': cls.get_required_methods(action_type),
                    'missing_methods': cls.get_required_methods(action_type)
                }
            user_id = current_user.id
        
        if cls.is_verified(user_id, action_type):
            return {'required': False, 'methods': []}
        
        required_methods = cls.get_required_methods(action_type)
        return {
            'required': True,
            'methods': required_methods,
            'missing_methods': required_methods
        }

    @classmethod
    def get_verification_status(cls, action_type: str, user_id: Optional[int] = None) -> Dict[str, Any]:
        """Get detailed verification status for an action."""
        if user_id is None:
            if not current_user or not current_user.is_authenticated:
                return {'verified': False, 'required_methods': cls.get_required_methods(action_type)}
            user_id = current_user.id
        
        required = cls.get_required_methods(action_type)
        is_done = cls.is_verified(user_id, action_type)
        
        return {
            'verified': is_done,
            'required_methods': required,
            'action': action_type,
            'user_id': user_id
        }

