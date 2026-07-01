# app/media/settings_service.py
"""
MediaSettingsService - Database-backed media configuration.
Reads from MediaSettings model (with Redis caching) and provides
effective settings that override config.py defaults.
"""

from app.media.models import MediaSettings


class MediaSettingsService:
    """
    Service for reading and writing media settings.
    Settings are stored in the database and cached in Redis.
    Falls back to config.py defaults if DB is unavailable.
    """

    @classmethod
    def get_all(cls) -> dict:
        """
        Get all media settings as a dictionary.
        Returns DB settings if available, otherwise falls back to Flask config.
        """
        try:
            settings = MediaSettings.get()
            return settings.to_dict()
        except Exception as e:
            # Fall back to Flask config defaults
            from flask import current_app
            return cls._get_config_defaults(current_app.config)

    @classmethod
    def get(cls, key: str, default=None):
        """Get a single setting by key."""
        settings = cls.get_all()
        return settings.get(key, default)

    @classmethod
    def update(cls, data: dict, updated_by_id: int = None) -> tuple:
        """
        Update media settings.
        data: dict of setting_name -> value
        Returns (success, error_message).
        """
        try:
            settings = MediaSettings.get()

            # Map incoming data to model columns
            field_mapping = {
                'virus_scan_enabled': 'virus_scan_enabled',
                'content_moderation_enabled': 'content_moderation_enabled',
                'perceptual_hash_enabled': 'perceptual_hash_enabled',
                'perceptual_hash_threshold': 'perceptual_hash_threshold',
                'max_photo_size_mb': 'max_photo_size_mb',
                'max_document_size_mb': 'max_document_size_mb',
                'upload_rate_limit': 'upload_rate_limit',
                'chunked_upload_rate_limit': 'chunked_upload_rate_limit',
                'webp_quality': 'webp_quality',
                'avif_quality': 'avif_quality',
                'jpeg_quality': 'jpeg_quality',
                'user_quota_mb': 'user_quota_mb',
                'host_quota_mb': 'host_quota_mb',
                'org_quota_mb': 'org_quota_mb',
                'quota_enforcement_enabled': 'quota_enforcement_enabled',
                'module_overrides': 'module_overrides',
                'cdn_base_url': 'cdn_base_url',
                'signed_url_expiry_seconds': 'signed_url_expiry_seconds',
            }

            for data_key, model_key in field_mapping.items():
                if data_key in data:
                    value = data[data_key]
                    # Type conversion
                    if model_key in ('max_photo_size_mb', 'max_document_size_mb',
                                     'perceptual_hash_threshold', 'webp_quality',
                                     'avif_quality', 'jpeg_quality', 'user_quota_mb',
                                     'host_quota_mb', 'org_quota_mb',
                                     'signed_url_expiry_seconds'):
                        value = int(value)
                    elif model_key in ('virus_scan_enabled', 'content_moderation_enabled',
                                       'perceptual_hash_enabled', 'quota_enforcement_enabled'):
                        value = bool(value)
                    elif model_key == 'module_overrides':
                        value = dict(value) if value else {}
                    setattr(settings, model_key, value)

            return settings.save(updated_by_id=updated_by_id)

        except Exception as e:
            return False, str(e)

    @classmethod
    def get_effective_config(cls) -> dict:
        """
        Get effective media configuration for use in uploads.
        Merges DB settings with Flask config defaults.
        This is what MediaService should use, not raw config.py values.
        """
        from flask import current_app

        db_settings = cls.get_all()
        config = current_app.config

        return {
            # Security features (DB overrides config)
            'virus_scan_enabled': db_settings.get('virus_scan_enabled',
                config.get('MEDIA_VIRUS_SCAN_ENABLED', True)),
            'content_moderation_enabled': db_settings.get('content_moderation_enabled',
                config.get('MEDIA_CONTENT_MODERATION_ENABLED', True)),
            'perceptual_hash_enabled': db_settings.get('perceptual_hash_enabled',
                config.get('MEDIA_PERCEPTUAL_HASH_ENABLED', True)),
            'perceptual_hash_threshold': db_settings.get('perceptual_hash_threshold',
                config.get('MEDIA_PERCEPTUAL_HASH_THRESHOLD', 6)),

            # Upload limits
            'max_photo_size': db_settings.get('max_photo_size_mb', 20) * 1024 * 1024,
            'max_document_size': db_settings.get('max_document_size_mb', 10) * 1024 * 1024,
            'upload_rate_limit': db_settings.get('upload_rate_limit',
                config.get('MEDIA_UPLOAD_RATE_LIMIT', '50 per minute')),
            'chunked_upload_rate_limit': db_settings.get('chunked_upload_rate_limit',
                config.get('MEDIA_CHUNK_UPLOAD_RATE_LIMIT', '100 per minute')),

            # Image quality
            'webp_quality': db_settings.get('webp_quality',
                config.get('IMAGE_QUALITY_WEBP', 75)),
            'avif_quality': db_settings.get('avif_quality',
                config.get('IMAGE_QUALITY_AVIF', 65)),
            'jpeg_quality': db_settings.get('jpeg_quality',
                config.get('IMAGE_QUALITY_JPEG', 82)),

            # Quotas
            'user_quota_bytes': db_settings.get('user_quota_mb', 500) * 1024 * 1024,
            'host_quota_bytes': db_settings.get('host_quota_mb', 5000) * 1024 * 1024,
            'org_quota_bytes': db_settings.get('org_quota_mb', 10000) * 1024 * 1024,
            'quota_enforcement_enabled': db_settings.get('quota_enforcement_enabled', True),

            # CDN
            'cdn_base_url': db_settings.get('cdn_base_url',
                config.get('CDN_BASE_URL', '')),
            'signed_url_expiry_seconds': db_settings.get('signed_url_expiry_seconds', 3600),

            # Module overrides
            'module_overrides': db_settings.get('module_overrides', {}),
        }

    @classmethod
    def _get_config_defaults(cls, config: dict) -> dict:
        """Extract media defaults from Flask config."""
        return {
            'virus_scan_enabled': config.get('MEDIA_VIRUS_SCAN_ENABLED', True),
            'content_moderation_enabled': config.get('MEDIA_CONTENT_MODERATION_ENABLED', True),
            'perceptual_hash_enabled': config.get('MEDIA_PERCEPTUAL_HASH_ENABLED', True),
            'perceptual_hash_threshold': config.get('MEDIA_PERCEPTUAL_HASH_THRESHOLD', 6),
            'max_photo_size_mb': config.get('MEDIA_MAX_PHOTO_SIZE', 20 * 1024 * 1024) // (1024 * 1024),
            'max_document_size_mb': config.get('MEDIA_MAX_DOCUMENT_SIZE', 10 * 1024 * 1024) // (1024 * 1024),
            'upload_rate_limit': config.get('MEDIA_UPLOAD_RATE_LIMIT', '50 per minute'),
            'chunked_upload_rate_limit': config.get('MEDIA_CHUNK_UPLOAD_RATE_LIMIT', '100 per minute'),
            'webp_quality': config.get('IMAGE_QUALITY_WEBP', 75),
            'avif_quality': config.get('IMAGE_QUALITY_AVIF', 65),
            'jpeg_quality': config.get('IMAGE_QUALITY_JPEG', 82),
            'user_quota_mb': config.get('MEDIA_USER_QUOTA', 500 * 1024 * 1024) // (1024 * 1024),
            'host_quota_mb': config.get('MEDIA_HOST_QUOTA', 5 * 1024 * 1024 * 1024) // (1024 * 1024),
            'org_quota_mb': config.get('MEDIA_ORG_QUOTA', 10 * 1024 * 1024 * 1024) // (1024 * 1024),
            'quota_enforcement_enabled': config.get('MEDIA_QUOTA_ENABLED', True),
            'module_overrides': config.get('MEDIA_MODULE_CONFIG', {}),
            'cdn_base_url': config.get('CDN_BASE_URL', ''),
            'signed_url_expiry_seconds': 3600,
        }
