# app/media/utils/quota_manager.py
"""
Per-user storage quota management.
Tracks and enforces storage limits per user to prevent abuse.
"""

from app.extensions import db
from app.media.models import Media
from flask import current_app


class QuotaManager:
    """
    Manage per-user storage quotas.
    Quotas are enforced at upload time and tracked in the database.
    """

    # Default quotas (can be overridden per module in config)
    DEFAULT_USER_QUOTA = 500 * 1024 * 1024  # 500MB per user
    DEFAULT_HOST_QUOTA = 5 * 1024 * 1024 * 1024  # 5GB per host
    DEFAULT_ORG_QUOTA = 10 * 1024 * 1024 * 1024  # 10GB per organization

    @classmethod
    def get_user_quota(cls, user_id: int, module: str = None) -> int:
        """
        Get storage quota for a user in bytes.
        Checks config for module-specific overrides.
        """
        config = current_app.config.get('MEDIA_MODULE_CONFIG', {}).get(module, {})

        # Check for module-specific quota
        if 'user_quota' in config:
            return config['user_quota']

        # Default based on user role (simplified)
        return cls.DEFAULT_USER_QUOTA

    @classmethod
    def get_user_usage(cls, user_id: int, module: str = None) -> int:
        """
        Calculate current storage usage for a user in bytes.
        Only counts non-deleted media.
        """
        query = db.session.query(Media).filter(
            Media.uploaded_by == user_id,
            Media.is_deleted == False,
            Media.file_size != None
        )

        if module:
            query = query.filter(Media.module == module)

        total = sum(m.file_size for m in query.all() if m.file_size)
        return total or 0

    @classmethod
    def check_quota(cls, user_id: int, file_size: int, module: str = None) -> tuple:
        """
        Check if user has enough quota for a new upload.
        Returns (has_quota, remaining_bytes, error_message).
        """
        quota = cls.get_user_quota(user_id, module)
        current_usage = cls.get_user_usage(user_id, module)
        remaining = quota - current_usage

        if file_size > remaining:
            return False, remaining, (
                f"Storage quota exceeded. "
                f"Used: {current_usage // (1024*1024)}MB / {quota // (1024*1024)}MB. "
                f"File size: {file_size // (1024*1024)}MB. "
                f"Remaining: {remaining // (1024*1024)}MB."
            )

        return True, remaining, ""

    @classmethod
    def enforce_quota(cls, user_id: int, file_size: int, module: str = None) -> bool:
        """
        Enforce quota check. Raises ValueError if quota exceeded.
        Returns True if upload is allowed.
        """
        has_quota, remaining, error = cls.check_quota(user_id, file_size, module)
        if not has_quota:
            raise ValueError(error)
        return True

    @classmethod
    def get_quota_status(cls, user_id: int, module: str = None) -> dict:
        """
        Get detailed quota status for a user.
        Returns dict with quota info for API responses.
        """
        quota = cls.get_user_quota(user_id, module)
        used = cls.get_user_usage(user_id, module)
        remaining = max(0, quota - used)
        percentage = (used / quota * 100) if quota > 0 else 0

        return {
            'quota_bytes': quota,
            'used_bytes': used,
            'remaining_bytes': remaining,
            'percentage_used': round(percentage, 1),
            'quota_mb': round(quota / (1024 * 1024), 1),
            'used_mb': round(used / (1024 * 1024), 1),
            'remaining_mb': round(remaining / (1024 * 1024), 1),
        }
