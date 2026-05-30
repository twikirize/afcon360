"""
Password Policy Enforcement

Implements strong password requirements with validation and expiration.
"""

import re
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from flask import current_app
from werkzeug.security import generate_password_hash


class PasswordPolicy:
    """Strong password policy enforcement."""
    
    def __init__(self):
        self.min_length = 12
        self.max_length = 128
        self.require_uppercase = True
        self.require_lowercase = True
        self.require_digits = True
        self.require_special = True
        self.forbidden_patterns = [
            r'password', r'123456', r'qwerty', r'admin', r'letmein',
            r'welcome', r'afcon360', r'wallet', r'test'
        ]
        self.forbidden_sequences = [
            '1234', '2345', '3456', '4567', '5678', '6789', '7890',
            'abcd', 'bcde', 'cdef', 'defg', 'efgh', 'fghi', 'ghij',
            'qwer', 'wert', 'erty', 'rtyu', 'tyui', 'yuio', 'uiop'
        ]
        self.max_age_days = 90
        self.history_count = 5  # Remember last 5 passwords
    
    def validate_password(self, password: str, user_info: Dict = None) -> Tuple[bool, List[str]]:
        """
        Validate password against policy.
        
        Returns:
            (is_valid, error_messages)
        """
        errors = []
        
        # Length checks
        if len(password) < self.min_length:
            errors.append(f"Password must be at least {self.min_length} characters long")
        
        if len(password) > self.max_length:
            errors.append(f"Password must not exceed {self.max_length} characters")
        
        # Character requirements
        if self.require_uppercase and not re.search(r'[A-Z]', password):
            errors.append("Password must contain at least one uppercase letter")
        
        if self.require_lowercase and not re.search(r'[a-z]', password):
            errors.append("Password must contain at least one lowercase letter")
        
        if self.require_digits and not re.search(r'\d', password):
            errors.append("Password must contain at least one digit")
        
        if self.require_special and not re.search(r'[!@#$%^&*()_+\-=\[\]{};:"\\|,.<>\/?]', password):
            errors.append("Password must contain at least one special character")
        
        # Forbidden patterns
        password_lower = password.lower()
        for pattern in self.forbidden_patterns:
            if re.search(pattern, password_lower):
                errors.append(f"Password cannot contain common patterns like '{pattern}'")
        
        # Forbidden sequences
        for seq in self.forbidden_sequences:
            if seq in password_lower:
                errors.append(f"Password cannot contain sequential characters like '{seq}'")
        
        # User information checks
        if user_info:
            # Check against email, username, phone
            for key, value in user_info.items():
                if value and isinstance(value, str):
                    value_lower = value.lower()
                    if value_lower in password_lower:
                        errors.append(f"Password cannot contain your {key}")
        
        return len(errors) == 0, errors
    
    def check_password_expiration(self, user) -> Tuple[bool, int]:
        """
        Check if password has expired.
        
        Returns:
            (is_expired, days_until_expiration)
        """
        if not user.password_changed_at:
            return True, 0
        
        days_since_change = (datetime.utcnow() - user.password_changed_at).days
        days_until_expiration = self.max_age_days - days_since_change
        
        return days_since_change >= self.max_age_days, days_until_expiration
    
    def is_password_in_history(self, user, new_password: str) -> bool:
        """Check if new password was used before."""
        # This would require password history storage
        # For now, return False (implement with password history table)
        return False
    
    def generate_password_requirements_text(self) -> str:
        """Generate user-friendly password requirements text."""
        requirements = []
        requirements.append(f"At least {self.min_length} characters")
        
        if self.require_uppercase:
            requirements.append("One uppercase letter")
        
        if self.require_lowercase:
            requirements.append("One lowercase letter")
        
        if self.require_digits:
            requirements.append("One digit")
        
        if self.require_special:
            requirements.append("One special character (!@#$%^&* etc.)")
        
        return "Password must contain: " + ", ".join(requirements)


# Password policy middleware
def enforce_password_policy(f):
    """Decorator to enforce password policy for sensitive operations."""
    from functools import wraps
    from flask import session, redirect, url_for, flash
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        if user_id:
            from app.identity.models.user import User
            from app.auth.password_policy import PasswordPolicy
            
            user = User.query.get(user_id)
            if user:
                policy = PasswordPolicy()
                is_expired, days_left = policy.check_password_expiration(user)
                
                if is_expired:
                    flash('Your password has expired. Please update it.', 'warning')
                    return redirect(url_for('auth.change_password'))
                elif days_left <= 7:
                    flash(f'Your password will expire in {days_left} days. Consider updating it.', 'info')
        
        return f(*args, **kwargs)
    
    return decorated_function
