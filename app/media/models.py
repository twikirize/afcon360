# app/media/models.py

import uuid
import json
import logging
from datetime import datetime, timezone
from sqlalchemy import (
    Column, BigInteger, String, Boolean, DateTime, Integer, Text, JSON, Index, UniqueConstraint, ForeignKey
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.extensions import db
from app.models.base import BaseModel

log = logging.getLogger(__name__)

_CACHE_KEY = "platform:media_settings"
_CACHE_TTL = 300  # 5 minutes


class MediaSettings(BaseModel):
    """
    Platform-wide media settings. Single-row table - use MediaSettings.get().
    All settings have safe defaults so the system works even before
    the admin has visited the settings page.
    """
    __tablename__ = "media_settings"

    # ── Security Features ────────────────────────────────────────────────────
    virus_scan_enabled = Column(
        Boolean, default=True, nullable=False,
        doc="Enable virus/malware scanning on uploads."
    )
    content_moderation_enabled = Column(
        Boolean, default=True, nullable=False,
        doc="Enable content moderation (dimensions, brightness, color checks)."
    )
    perceptual_hash_enabled = Column(
        Boolean, default=True, nullable=False,
        doc="Enable perceptual hashing for near-duplicate detection."
    )
    perceptual_hash_threshold = Column(
        Integer, default=6, nullable=False,
        doc="Hamming distance threshold for near-duplicate detection (0-64, lower=stricter)."
    )

    # ── Upload Limits ────────────────────────────────────────────────────────
    max_photo_size_mb = Column(
        Integer, default=20, nullable=False,
        doc="Maximum photo upload size in MB."
    )
    max_document_size_mb = Column(
        Integer, default=10, nullable=False,
        doc="Maximum document upload size in MB."
    )
    upload_rate_limit = Column(
        String(50), default="50 per minute", nullable=False,
        doc="Rate limit for uploads (Flask-Limiter format)."
    )
    chunked_upload_rate_limit = Column(
        String(50), default="100 per minute", nullable=False,
        doc="Rate limit for chunked upload chunks."
    )

    # ── Image Optimization ───────────────────────────────────────────────────
    webp_quality = Column(
        Integer, default=75, nullable=False,
        doc="WebP compression quality (0-100)."
    )
    avif_quality = Column(
        Integer, default=65, nullable=False,
        doc="AVIF compression quality (0-100)."
    )
    jpeg_quality = Column(
        Integer, default=82, nullable=False,
        doc="JPEG compression quality (0-100)."
    )

    # ── Storage Quotas (bytes) ───────────────────────────────────────────────
    user_quota_mb = Column(
        Integer, default=500, nullable=False,
        doc="Storage quota per regular user in MB."
    )
    host_quota_mb = Column(
        Integer, default=5000, nullable=False,
        doc="Storage quota per host in MB."
    )
    org_quota_mb = Column(
        Integer, default=10000, nullable=False,
        doc="Storage quota per organization in MB."
    )
    quota_enforcement_enabled = Column(
        Boolean, default=True, nullable=False,
        doc="Enforce storage quotas at upload time."
    )

    # ── Access Control ────────────────────────────────────────────────────────
    # Owner-controlled: which roles are authorized to manage media settings
    # Default: only owner can manage. Owner can grant admin/super_admin access.
    authorized_manager_roles = Column(
        JSON, nullable=False, default=list,
        doc="List of role names authorized to manage media settings (owner-controlled)."
    )

    # ── Module-Specific Overrides (JSON) ─────────────────────────────────────
    # Allows per-module max_size and allowed_types overrides
    # Format: {"accommodation": {"max_size_mb": 25, "allowed_types": [...]}, ...}
    module_overrides = Column(
        JSON, nullable=False, default=dict,
        doc="Per-module overrides for upload limits and allowed types."
    )

    # ── CDN & Delivery ───────────────────────────────────────────────────────
    cdn_base_url = Column(
        String(500), nullable=True,
        doc="CDN base URL (e.g., https://cdn.example.com). Empty = serve from storage."
    )
    signed_url_expiry_seconds = Column(
        Integer, default=3600, nullable=False,
        doc="Expiry time for signed URLs (seconds)."
    )

    # ── Meta ─────────────────────────────────────────────────────────────────
    updated_by_id = Column(BigInteger, nullable=True)
    notes = Column(Text, nullable=True,
                   doc="Internal notes about media settings configuration.")

    # ── Class Methods ────────────────────────────────────────────────────────

    @classmethod
    def get(cls) -> "MediaSettings":
        """
        Return the singleton settings row, creating it with defaults if
        it doesn't exist yet. Caches in Redis for 5 minutes.
        """
        # Try Redis cache first
        try:
            from app.extensions import redis_client
            if redis_client:
                cached = redis_client.get(_CACHE_KEY)
                if cached:
                    data = json.loads(cached)
                    obj = cls()
                    for k, v in data.items():
                        if hasattr(obj, k):
                            setattr(obj, k, v)
                    return obj
        except Exception as e:
            log.debug(f"MediaSettings cache miss: {e}")

        # Fall back to DB
        row = cls.query.first()
        if not row:
            row = cls()
            db.session.add(row)
            try:
                db.session.commit()
                log.info("MediaSettings: created default settings row")
            except Exception:
                db.session.rollback()
                row = cls.query.first() or cls()

        # Cache it
        cls._cache(row)
        return row

    @classmethod
    def _cache(cls, row: "MediaSettings"):
        """Write settings to Redis cache."""
        try:
            from app.extensions import redis_client
            if redis_client:
                data = {
                    c.key: getattr(row, c.key)
                    for c in cls.__table__.columns
                    if not c.key.startswith('_')
                }
                redis_client.setex(_CACHE_KEY, _CACHE_TTL, json.dumps(data, default=str))
        except Exception as e:
            log.debug(f"MediaSettings cache write failed: {e}")

    @classmethod
    def invalidate_cache(cls):
        """Clear the Redis cache - call after saving changes."""
        try:
            from app.extensions import redis_client
            if redis_client:
                redis_client.delete(_CACHE_KEY)
        except Exception:
            pass

    def save(self, updated_by_id: int = None):
        """Persist changes and invalidate cache."""
        if updated_by_id:
            self.updated_by_id = updated_by_id
        try:
            db.session.commit()
            self.__class__.invalidate_cache()
            log.info(f"MediaSettings updated by user {updated_by_id}")
            return True, None
        except Exception as e:
            db.session.rollback()
            log.error(f"MediaSettings save failed: {e}")
            return False, str(e)

    def to_dict(self) -> dict:
        """Return settings as a dictionary for API/template use."""
        return {
            'virus_scan_enabled': self.virus_scan_enabled,
            'content_moderation_enabled': self.content_moderation_enabled,
            'perceptual_hash_enabled': self.perceptual_hash_enabled,
            'perceptual_hash_threshold': self.perceptual_hash_threshold,
            'max_photo_size_mb': self.max_photo_size_mb,
            'max_document_size_mb': self.max_document_size_mb,
            'upload_rate_limit': self.upload_rate_limit,
            'chunked_upload_rate_limit': self.chunked_upload_rate_limit,
            'webp_quality': self.webp_quality,
            'avif_quality': self.avif_quality,
            'jpeg_quality': self.jpeg_quality,
            'user_quota_mb': self.user_quota_mb,
            'host_quota_mb': self.host_quota_mb,
            'org_quota_mb': self.org_quota_mb,
            'quota_enforcement_enabled': self.quota_enforcement_enabled,
            'module_overrides': self.module_overrides or {},
            'cdn_base_url': self.cdn_base_url,
            'signed_url_expiry_seconds': self.signed_url_expiry_seconds,
        }

    def __repr__(self):
        return (
            f"<MediaSettings virus_scan={self.virus_scan_enabled} "
            f"moderation={self.content_moderation_enabled} "
            f"quota={self.quota_enforcement_enabled}>"
        )


class Media(BaseModel):
    """
    Unified media record for all modules.
    Inherits: id (BIGINT PK), is_deleted, deleted_at, created_at, updated_at from BaseModel.
    """
    __tablename__ = "media"

    # Public identity (never expose id BIGINT externally)
    public_id = Column(String(64), unique=True, nullable=False, index=True,
                       default=lambda: str(uuid.uuid4()))

    # Processing tracking - ✅ FIX: Add server_default for NOT NULL columns
    processing_attempts = Column(Integer, default=0, nullable=False, server_default='0')
    processing_started_at = Column(DateTime(timezone=True), nullable=True)
    processing_completed_at = Column(DateTime(timezone=True), nullable=True)
    failed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    notified = Column(Boolean, default=False, nullable=False, server_default='false')
    cleaned_at = Column(DateTime(timezone=True), nullable=True)

    # Processing metadata
    processing_metadata = Column(JSONB, nullable=True)

    # Module context — which module and which entity this belongs to
    module = Column(String(50), nullable=False, index=True)
    # entity_id is the PUBLIC UUID of the owning entity (not BIGINT)
    # e.g., property.public_id, user.public_id, kyc_record.reference_code
    entity_id = Column(String(64), nullable=False, index=True)

    # Uploader — internal BIGINT FK (never exposed)
    uploaded_by = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Media classification — using String per project rules (no sa.Enum)
    media_type = Column(
        String(50), nullable=False, default="photo"
    )

    # Storage
    storage_key = Column(String(500), nullable=True)
    storage_backend = Column(String(20), nullable=False, default="local")

    # For video_url type: YouTube video ID
    video_url = Column(String(500), nullable=True)

    # File metadata
    original_filename = Column(String(255), nullable=True)
    file_size = Column(Integer, nullable=True)
    mime_type = Column(String(100), nullable=True)
    sha256_hash = Column(String(64), nullable=True, index=True)
    perceptual_hash = Column(String(64), nullable=True, index=True)

    # Image/video dimensions
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    duration = Column(Integer, nullable=True)
    thumbnail_url = Column(String(500), nullable=True)
    is_animated = Column(Boolean, default=False)

    # Chunked upload session
    upload_session_id = Column(String(64), nullable=True, index=True)

    # Processing — using String per project rules (no sa.Enum)
    status = Column(
        String(20), nullable=False, default="pending", index=True
    )

    # Generated URLs — JSON dict of size variants
    urls = Column(JSON, nullable=False, default=dict)

    # Display
    caption = Column(String(300), nullable=True)
    display_order = Column(Integer, default=0)
    is_cover = Column(Boolean, default=False)

    # Access control
    is_public = Column(Boolean, default=True, nullable=False)

    # Relationships
    processing_jobs = relationship("MediaProcessingJob", backref="media", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index("ix_media_module_entity", "module", "entity_id"),
        Index("ix_media_status_created", "status", "created_at"),
        Index("ix_media_sha256", "sha256_hash"),
        UniqueConstraint("public_id", name="uq_media_public_id"),
    )


class MediaProcessingJob(BaseModel):
    """
    Tracks async Celery processing jobs per media item.
    Allows polling for status without hitting Celery directly.
    Inherits: id (BIGINT PK), is_deleted, deleted_at, created_at, updated_at from BaseModel.
    """
    __tablename__ = "media_processing_jobs"

    media_id = Column(BigInteger, ForeignKey("media.id", ondelete="CASCADE"), nullable=False)
    celery_task_id = Column(String(64), nullable=True, index=True)
    job_type = Column(String(50), nullable=False)  # optimize, thumbnail, validate
    status = Column(String(20), nullable=False, default="queued")
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)
    result = Column(JSON, nullable=True)

    # Indexes
    __table_args__ = (
        Index("ix_mpj_celery_task", "celery_task_id"),
        Index("ix_mpj_media_id", "media_id"),
    )
