"""
Session Management with Timeout and Security

Implements secure session handling with timeout, rotation, and invalidation.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from flask import session, current_app, request, abort
from flask_login import current_user
import uuid
import hashlib


class SessionManager:
    """Secure session management with timeout and rotation."""
    
    def __init__(self):
        self.default_timeout_minutes = 30
        self.max_timeout_minutes = 120
        self.warning_minutes = 5
        self.session_rotation_interval = 15  # minutes
    
    def get_session_timeout(self, user) -> int:
        """Get session timeout based on user role and security level."""
        if not user:
            return self.default_timeout_minutes
        
        # Extended timeout for trusted users
        if hasattr(user, 'is_app_owner') and user.is_app_owner():
            return self.max_timeout_minutes
        
        # Shorter timeout for high-risk operations
        if hasattr(user, 'kyc_level') and user.kyc_level < 2:
            return 15
        
        # Default timeout
        return self.default_timeout_minutes
    
    def is_session_expired(self) -> bool:
        """Check if current session has expired."""
        if 'session_created_at' not in session:
            return True
        
        session_age = datetime.utcnow() - datetime.fromisoformat(session['session_created_at'])
        timeout_minutes = current_app.config.get('SESSION_TIMEOUT_MINUTES', self.default_timeout_minutes)
        
        return session_age.total_seconds() > (timeout_minutes * 60)
    
    def should_rotate_session(self) -> bool:
        """Check if session should be rotated (security measure)."""
        if 'last_rotation' not in session:
            return True
        
        last_rotation = datetime.fromisoformat(session['last_rotation'])
        rotation_age = datetime.utcnow() - last_rotation
        
        return rotation_age.total_seconds() > (self.session_rotation_interval * 60)
    
    def rotate_session_id(self):
        """Rotate session ID for security."""
        if not session:
            return
        
        # Store session data
        session_data = dict(session)
        
        # Clear session
        session.clear()
        
        # Regenerate session ID
        session.permanent = True
        
        # Restore session data with new timestamps
        for key, value in session_data.items():
            if key not in ['session_created_at', 'last_rotation', 'session_id']:
                session[key] = value
        
        session['session_created_at'] = datetime.utcnow().isoformat()
        session['last_rotation'] = datetime.utcnow().isoformat()
        session['session_id'] = str(uuid.uuid4())
    
    def create_secure_session(self, user, remember_me: bool = False):
        """Create a secure session with proper metadata."""
        session.clear()
        
        # Session metadata
        session['session_created_at'] = datetime.utcnow().isoformat()
        session['last_rotation'] = datetime.utcnow().isoformat()
        session['session_id'] = str(uuid.uuid4())
        session['user_agent_hash'] = self._hash_user_agent()
        session['ip_address'] = request.remote_addr
        session['timeout_minutes'] = self.get_session_timeout(user)
        
        # Security flags
        session['authenticated'] = True
        session['mfa_verified'] = not user.mfa_enabled  # Skip MFA if not enabled
        
        # User data
        session['user_id'] = user.id
        session['public_id'] = user.public_id
        
        # Remember me handling
        if remember_me:
            session.permanent = True
            # Set extended timeout for remember me
            session['timeout_minutes'] = min(session['timeout_minutes'] * 2, self.max_timeout_minutes)
        else:
            session.permanent = False
    
    def validate_session_integrity(self) -> bool:
        """Validate session integrity (IP, user agent, etc.)."""
        if not current_user.is_authenticated:
            return False
        
        # Check user agent consistency
        current_user_agent_hash = self._hash_user_agent()
        stored_user_agent_hash = session.get('user_agent_hash')
        
        if stored_user_agent_hash and current_user_agent_hash != stored_user_agent_hash:
            current_app.logger.warning(f"Session integrity violation: User agent changed for user {current_user.id}")
            return False
        
        # Check IP address consistency (optional, can be disabled for mobile users)
        current_ip = request.remote_addr
        stored_ip = session.get('ip_address')
        
        if stored_ip and current_ip != stored_ip:
            current_app.logger.warning(f"Session integrity warning: IP changed from {stored_ip} to {current_ip} for user {current_user.id}")
            # Don't invalidate session for IP changes (mobile users)
        
        return True
    
    def _hash_user_agent(self) -> str:
        """Hash user agent for session integrity checking."""
        user_agent = request.user_agent.string if request.user_agent else ""
        return hashlib.sha256(user_agent.encode()).hexdigest()
    
    def get_session_time_remaining(self) -> Dict[str, Any]:
        """Get session time remaining information."""
        if 'session_created_at' not in session:
            return {'expired': True, 'remaining_seconds': 0}
        
        session_age = datetime.utcnow() - datetime.fromisoformat(session['session_created_at'])
        timeout_seconds = session.get('timeout_minutes', self.default_timeout_minutes) * 60
        remaining_seconds = timeout_seconds - session_age.total_seconds()
        
        return {
            'expired': remaining_seconds <= 0,
            'remaining_seconds': max(0, int(remaining_seconds)),
            'warning': 0 < remaining_seconds <= (self.warning_minutes * 60)
        }
    
    def invalidate_session(self, reason: str = "manual"):
        """Invalidate current session."""
        if current_user.is_authenticated:
            current_app.logger.info(f"Session invalidated for user {current_user.id}: {reason}")
        
        session.clear()
    
    def invalidate_all_user_sessions(self, user_id: int):
        """Invalidate all sessions for a user (requires session store)."""
        # This would require Redis or database session store
        # For now, just log the action
        current_app.logger.info(f"All sessions invalidated for user {user_id}")


# Session middleware
def require_valid_session(f):
    """Decorator to require valid session with integrity checks."""
    from functools import wraps
    from flask import redirect, url_for, flash
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from app.auth.session_management import SessionManager
        
        session_manager = SessionManager()
        
        # Check if session exists and is valid
        if not session.get('authenticated'):
            flash('Session expired. Please login again.', 'warning')
            return redirect(url_for('auth.login'))
        
        # Check session expiration
        if session_manager.is_session_expired():
            flash('Session expired. Please login again.', 'warning')
            session_manager.invalidate_session("expired")
            return redirect(url_for('auth.login'))
        
        # Validate session integrity
        if not session_manager.validate_session_integrity():
            flash('Session security violation. Please login again.', 'error')
            session_manager.invalidate_session("integrity_violation")
            return redirect(url_for('auth.login'))
        
        # Rotate session if needed
        if session_manager.should_rotate_session():
            session_manager.rotate_session_id()
        
        return f(*args, **kwargs)
    
    return decorated_function


# Session timeout warning
def check_session_timeout():
    """Check session timeout and set warning if needed."""
    from app.auth.session_management import SessionManager
    
    session_manager = SessionManager()
    session_info = session_manager.get_session_time_remaining()
    
    if session_info['expired']:
        session_manager.invalidate_session("expired")
        return False
    
    if session_info['warning']:
        session['session_warning'] = True
        session['session_expires_in'] = session_info['remaining_seconds']
    
    return True
