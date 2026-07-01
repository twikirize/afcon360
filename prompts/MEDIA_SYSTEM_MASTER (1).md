# AFCON360 — MEDIA SYSTEM MASTER DOCUMENT
## Chief Product Engineer Brief for Kilo Agent Orchestration

---

## DOCUMENT METADATA

| Field | Value |
|-------|-------|
| Version | 1.0 |
| Date | 2026-06-27 |
| Status | Active — Implementation Ready |
| Authority | Chief Product Engineer (Claude) |
| Executor | Kilo Agent (Orchestrator → Planner → Agent → Inspector → Verifier) |
| Codebase | AFCON360 Flask Application |
| Deployment | Oracle Cloud Free Tier (ARM) + Docker + Local Dev |

---

## PART 1: GOAL

### 1.1 What We Are Building

A **unified, environment-intelligent media management system** for AFCON360 that:

1. Lives as an **independent module** at `app/media/` with its own blueprint, models, service, and routes
2. Serves **all existing modules** (accommodation, tourism, events, transport, KYC, user profile) through a single consistent API
3. Handles **photos and videos** — photos stored on OCI Object Storage, videos handled via YouTube URL submission (no video storage)
4. Works **identically in local dev and on Oracle Cloud** via environment-driven configuration, with zero code changes between environments
5. Processes uploads **asynchronously via Celery** — web workers never handle file I/O directly
6. Applies **WebP/AVIF optimization** for all photos to minimize bandwidth (Africa-first)
7. Integrates with the **existing ForensicAuditService** for all KYC media (most sensitive tier)
8. Respects the **dual ID system** (public_id UUIDs externally, BIGINT internally) from `IDENTITY_POLICIES.md`
9. Follows **BaseModel inheritance** for all new models (soft delete, timestamps included)
10. Is **CSRF-safe** on all upload endpoints

### 1.2 What We Are NOT Building (Deferred)

- Video transcoding / HLS streaming (use YouTube URL submission instead)
- Face detection / OCR (Phase 3, Month 2+)
- Service Worker offline support (CSP conflict, defer until CSP allows `worker-src`)
- CDN integration (Oracle CDN or CloudFront — when funded)
- AI content moderation (ClamAV virus scan only for now)
- Multi-region replication (single Oracle region for now)

### 1.3 Primary Use Case (Immediate)

**Accommodation module** — hotel property photos and room photos. This is the first integration target. Host creates a listing, uploads photos directly through the media uploader component.

---

## PART 2: ARCHITECTURE DECISIONS

### 2.1 Storage Backend — Environment Intelligence

```
LOCAL DEV  →  Local filesystem  (/tmp/afcon360_media/ or configured path)
ORACLE     →  OCI Object Storage (S3-compatible API)
FUTURE     →  AWS S3 / Cloudflare R2 (config-swap only, no code change)
```

The `StorageBackend` abstraction means the rest of the system never knows or cares which backend is active. Switch is purely via `STORAGE_TYPE` env variable.

**OCI Object Storage Notes:**
- Uses S3-compatible API (`boto3` works directly with OCI endpoint)
- Region endpoint format: `https://{namespace}.compat.objectstorage.{region}.oraclecloud.com`
- Free tier: 20GB total object storage
- No egress fees within OCI

### 2.2 Upload Flow — Async First

```
Browser FormData POST
    → /api/media/upload/{module}
        → Validate (type, size, magic bytes)
        → Store raw file to storage backend
        → Create Media DB record (status=processing)
        → Queue Celery task: process_media.delay(media_id)
        → Return 202 Accepted + media_id + polling URL
            → Celery Worker:
                → Generate WebP variants (tiny, small, medium, large)
                → Update Media record (status=ready, urls=JSON)
                → ForensicAuditService.log_completion() if KYC module
    → Frontend polls /api/media/status/{media_id}
        → When status=ready, display image
```

**Why not presigned URLs yet:** OCI presigned URLs require a more complex CORS setup. For current scale (pre-global launch), direct upload through Flask is acceptable given Celery offloads processing immediately. Presigned URLs are the Phase 2 upgrade path.

### 2.3 Video Strategy — YouTube URL Submission

```
Host submits YouTube URL
    → Validate: must be youtube.com or youtu.be domain
    → Extract video ID
    → Store as Media record with media_type='video_url', storage_key=youtube_video_id
    → Return embed URL for rendering
    → No file storage, no transcoding, no bandwidth cost
```

This is the right call for current scale and funding level. YouTube handles global CDN, adaptive bitrate, and mobile optimization for free.

### 2.4 Module Integration Pattern

Existing modules keep their URL columns. The Media module writes back to those columns after processing. No schema changes to existing module tables (except Events which needs a media model — addressed below).

```python
# Pattern: Module calls MediaService, gets URL back, stores in its own column
result = MediaService.upload(file, module='accommodation', entity_id=property.public_id, ...)
property.main_image = result['urls']['medium']  # Store CDN/storage URL
```

---

## PART 3: FILE STRUCTURE

```
app/
└── media/                          # NEW — Independent media module
    ├── __init__.py                 # Blueprint registration
    ├── models.py                   # Media model + MediaProcessingJob model
    ├── routes.py                   # Upload, delete, status, youtube endpoints
    ├── service.py                  # MediaService — core business logic
    ├── tasks.py                    # Celery tasks (optimize, process)
    ├── storage/
    │   ├── __init__.py             # StorageBackend base class
    │   ├── local.py                # LocalStorageBackend
    │   └── oci.py                  # OCIStorageBackend (S3-compatible)
    ├── processors/
    │   ├── __init__.py
    │   ├── image.py                # ImageProcessor (Pillow — WebP/AVIF)
    │   └── video.py                # YouTubeURLValidator (no transcoding)
    └── validators.py               # UploadValidator (type, size, magic bytes)

app/utils/
└── media_helpers.py                # Jinja2 helpers: media_url(), srcset()

static/
├── js/
│   └── global/
│       └── media-manager.js        # Drag-drop uploader + polling
└── css/
    └── modules/
        └── media.css               # Upload component styles

templates/
└── components/
    ├── media_upload.html           # Reusable upload component
    └── media_gallery.html          # Gallery display component

migrations/
└── versions/
    └── add_media_tables.py         # Media + MediaProcessingJob tables
```

---

## PART 4: DATA MODELS

### 4.1 Media Model

```python
# app/media/models.py

class Media(BaseModel):
    """
    Unified media record for all modules.
    Inherits: id (BIGINT PK), is_deleted, deleted_at, created_at, updated_at from BaseModel.
    """
    __tablename__ = "media"

    # Public identity (never expose id BIGINT externally)
    public_id = Column(String(64), unique=True, nullable=False, index=True,
                       default=lambda: str(uuid.uuid4()))

    # Module context — which module and which entity this belongs to
    module = Column(String(50), nullable=False, index=True)
    # entity_id is the PUBLIC UUID of the owning entity (not BIGINT)
    # e.g., property.public_id, user.public_id, kyc_record.reference_code
    entity_id = Column(String(64), nullable=False, index=True)

    # Uploader — internal BIGINT FK (never exposed)
    uploaded_by = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Media classification
    media_type = Column(
        Enum("photo", "document", "video_url", name="media_type_enum"),
        nullable=False, default="photo"
    )

    # Storage
    storage_key = Column(String(500), nullable=True)      # Path/key in storage backend
    storage_backend = Column(String(20), nullable=False, default="local")  # local, oci, s3

    # For video_url type: YouTube video ID
    video_url = Column(String(500), nullable=True)

    # File metadata
    original_filename = Column(String(255), nullable=True)
    file_size = Column(Integer, nullable=True)            # bytes
    mime_type = Column(String(100), nullable=True)
    sha256_hash = Column(String(64), nullable=True, index=True)  # deduplication

    # Processing
    status = Column(
        Enum("pending", "processing", "ready", "failed", name="media_status_enum"),
        nullable=False, default="pending", index=True
    )
    error_message = Column(Text, nullable=True)

    # Generated URLs — JSON dict of size variants
    # Format: {"original": "url", "tiny": "url", "small": "url",
    #          "medium": "url", "large": "url"}
    urls = Column(JSON, nullable=False, default=dict)

    # Display
    caption = Column(String(300), nullable=True)
    display_order = Column(Integer, default=0)
    is_cover = Column(Boolean, default=False)

    # Access control
    is_public = Column(Boolean, default=True, nullable=False)
    # Private media (KYC docs, identity) requires signed URL

    # Indexes
    __table_args__ = (
        Index("ix_media_module_entity", "module", "entity_id"),
        Index("ix_media_status_created", "status", "created_at"),
        Index("ix_media_sha256", "sha256_hash"),
        UniqueConstraint("public_id", name="uq_media_public_id"),
    )
```

### 4.2 MediaProcessingJob Model

```python
class MediaProcessingJob(BaseModel):
    """
    Tracks async Celery processing jobs per media item.
    Allows polling for status without hitting Celery directly.
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

    media = relationship("Media", backref="processing_jobs")
```

---

## PART 5: ENVIRONMENT CONFIGURATION

### 5.1 Config Variables to Add to `app/config.py`

```python
# ── Media / Storage ────────────────────────────────────────────────────────
STORAGE_TYPE = os.getenv('STORAGE_TYPE', 'local')  # local | oci | s3

# Local storage (dev)
MEDIA_LOCAL_PATH = os.getenv('MEDIA_LOCAL_PATH', '/tmp/afcon360_media')
MEDIA_LOCAL_URL_PREFIX = os.getenv('MEDIA_LOCAL_URL_PREFIX', '/media/files')

# OCI Object Storage (production Oracle)
OCI_NAMESPACE = os.getenv('OCI_NAMESPACE')           # Oracle tenancy namespace
OCI_BUCKET_NAME = os.getenv('OCI_BUCKET_NAME', 'afcon360-media')
OCI_REGION = os.getenv('OCI_REGION', 'eu-frankfurt-1')
OCI_ACCESS_KEY = os.getenv('OCI_ACCESS_KEY')         # OCI Customer Secret Key (Access Key)
OCI_SECRET_KEY = os.getenv('OCI_SECRET_KEY')         # OCI Customer Secret Key (Secret)
OCI_ENDPOINT_URL = os.getenv(
    'OCI_ENDPOINT_URL',
    f"https://{os.getenv('OCI_NAMESPACE', '')}.compat.objectstorage."
    f"{os.getenv('OCI_REGION', 'eu-frankfurt-1')}.oraclecloud.com"
)
CDN_BASE_URL = os.getenv('CDN_BASE_URL', '')         # Empty = serve from storage directly

# Upload limits
MEDIA_MAX_PHOTO_SIZE = int(os.getenv('MEDIA_MAX_PHOTO_SIZE', str(20 * 1024 * 1024)))  # 20MB
MEDIA_MAX_DOCUMENT_SIZE = int(os.getenv('MEDIA_MAX_DOCUMENT_SIZE', str(10 * 1024 * 1024)))  # 10MB
MEDIA_UPLOAD_RATE_LIMIT = os.getenv('MEDIA_UPLOAD_RATE_LIMIT', '50 per minute')

# Image optimization
IMAGE_QUALITY_WEBP = int(os.getenv('IMAGE_QUALITY_WEBP', '75'))
IMAGE_QUALITY_AVIF = int(os.getenv('IMAGE_QUALITY_AVIF', '65'))
IMAGE_QUALITY_JPEG = int(os.getenv('IMAGE_QUALITY_JPEG', '82'))

# Module permissions — which roles can upload to which modules
MEDIA_MODULE_CONFIG = {
    'accommodation': {
        'max_size': 20 * 1024 * 1024,
        'allowed_types': ['image/jpeg', 'image/png', 'image/webp', 'image/heic', 'image/heif'],
        'allowed_roles': ['owner', 'super_admin', 'admin', 'accommodation_admin'],
        'allow_host': True,   # Hosts (org members) can upload their own property photos
        'is_public': True,
    },
    'user': {
        'max_size': 5 * 1024 * 1024,
        'allowed_types': ['image/jpeg', 'image/png', 'image/webp'],
        'allowed_roles': [],  # Any authenticated user can upload their own avatar
        'allow_self': True,
        'is_public': True,
    },
    'kyc': {
        'max_size': 10 * 1024 * 1024,
        'allowed_types': ['image/jpeg', 'image/png', 'application/pdf'],
        'allowed_roles': [],  # User uploads their own KYC docs
        'allow_self': True,
        'is_public': False,   # Private — signed URLs only
        'audit_required': True,  # ForensicAuditService on every operation
    },
    'transport': {
        'max_size': 20 * 1024 * 1024,
        'allowed_types': ['image/jpeg', 'image/png', 'image/webp'],
        'allowed_roles': ['owner', 'super_admin', 'admin', 'transport_admin'],
        'allow_driver': True,
        'is_public': True,
    },
    'events': {
        'max_size': 20 * 1024 * 1024,
        'allowed_types': ['image/jpeg', 'image/png', 'image/webp'],
        'allowed_roles': ['owner', 'super_admin', 'admin', 'event_manager'],
        'allow_org': True,    # Org admins can upload for their own events
        'is_public': True,
    },
    'tourism': {
        'max_size': 20 * 1024 * 1024,
        'allowed_types': ['image/jpeg', 'image/png', 'image/webp'],
        'allowed_roles': ['owner', 'super_admin', 'admin', 'tourism_admin'],
        'is_public': True,
    },
}
```

### 5.2 Docker / Environment Files

**`.env.local` (developer machine):**
```bash
STORAGE_TYPE=local
MEDIA_LOCAL_PATH=/tmp/afcon360_media
MEDIA_LOCAL_URL_PREFIX=/media/files
```

**`.env.oracle` (Oracle Cloud VM):**
```bash
STORAGE_TYPE=oci
OCI_NAMESPACE=your_tenancy_namespace
OCI_BUCKET_NAME=afcon360-media
OCI_REGION=eu-frankfurt-1
OCI_ACCESS_KEY=your_oci_access_key
OCI_SECRET_KEY=your_oci_secret_key
OCI_ENDPOINT_URL=https://your_namespace.compat.objectstorage.eu-frankfurt-1.oraclecloud.com
CDN_BASE_URL=
```

**OCI Customer Secret Keys Setup (Kilo must document this in report):**
1. Oracle Console → Identity → Users → Your User → Customer Secret Keys
2. Generate key → copy Access Key + Secret Key immediately (secret not shown again)
3. Namespace: Oracle Console → Object Storage → Bucket → Namespace shown in bucket details

---

## PART 6: IMPLEMENTATION SPECIFICATION

### 6.1 StorageBackend Abstraction

```python
# app/media/storage/__init__.py

class StorageBackend:
    """Abstract base — all backends implement this interface."""

    def save(self, file_obj, storage_key: str, content_type: str) -> str:
        """Save file. Returns public URL or storage path."""
        raise NotImplementedError

    def delete(self, storage_key: str) -> bool:
        raise NotImplementedError

    def get_url(self, storage_key: str, expires_in: int = None) -> str:
        """Get URL. expires_in=None for public URL, int for signed URL (seconds)."""
        raise NotImplementedError

    def exists(self, storage_key: str) -> bool:
        raise NotImplementedError


def get_storage_backend() -> StorageBackend:
    """
    Factory — returns correct backend based on STORAGE_TYPE env var.
    Called once per request/task, not at import time.
    """
    from flask import current_app
    storage_type = current_app.config.get('STORAGE_TYPE', 'local')

    if storage_type == 'oci':
        from app.media.storage.oci import OCIStorageBackend
        return OCIStorageBackend()
    elif storage_type == 's3':
        from app.media.storage.s3 import S3StorageBackend
        return S3StorageBackend()
    else:
        from app.media.storage.local import LocalStorageBackend
        return LocalStorageBackend()
```

### 6.2 OCI Storage Backend (S3-Compatible)

```python
# app/media/storage/oci.py

import boto3
from botocore.client import Config as BotoConfig

class OCIStorageBackend(StorageBackend):
    """
    Oracle Cloud Object Storage via S3-compatible API.
    Uses boto3 with OCI endpoint.
    """

    def _get_client(self):
        from flask import current_app
        cfg = current_app.config
        return boto3.client(
            's3',
            region_name=cfg['OCI_REGION'],
            endpoint_url=cfg['OCI_ENDPOINT_URL'],
            aws_access_key_id=cfg['OCI_ACCESS_KEY'],
            aws_secret_access_key=cfg['OCI_SECRET_KEY'],
            config=BotoConfig(signature_version='s3')
        )

    def save(self, file_obj, storage_key: str, content_type: str) -> str:
        from flask import current_app
        client = self._get_client()
        bucket = current_app.config['OCI_BUCKET_NAME']
        client.upload_fileobj(
            file_obj,
            bucket,
            storage_key,
            ExtraArgs={
                'ContentType': content_type,
                'ACL': 'public-read'  # Accommodation photos are public
            }
        )
        cdn_base = current_app.config.get('CDN_BASE_URL', '')
        if cdn_base:
            return f"{cdn_base}/{storage_key}"
        return f"{current_app.config['OCI_ENDPOINT_URL']}/{bucket}/{storage_key}"

    def delete(self, storage_key: str) -> bool:
        from flask import current_app
        client = self._get_client()
        client.delete_object(
            Bucket=current_app.config['OCI_BUCKET_NAME'],
            Key=storage_key
        )
        return True

    def get_url(self, storage_key: str, expires_in: int = None) -> str:
        from flask import current_app
        if expires_in:
            # Signed URL for private content (KYC docs)
            client = self._get_client()
            return client.generate_presigned_url(
                'get_object',
                Params={'Bucket': current_app.config['OCI_BUCKET_NAME'], 'Key': storage_key},
                ExpiresIn=expires_in
            )
        cdn_base = current_app.config.get('CDN_BASE_URL', '')
        bucket = current_app.config['OCI_BUCKET_NAME']
        endpoint = current_app.config['OCI_ENDPOINT_URL']
        base = cdn_base if cdn_base else f"{endpoint}/{bucket}"
        return f"{base}/{storage_key}"

    def exists(self, storage_key: str) -> bool:
        from flask import current_app
        try:
            client = self._get_client()
            client.head_object(
                Bucket=current_app.config['OCI_BUCKET_NAME'],
                Key=storage_key
            )
            return True
        except Exception:
            return False
```

### 6.3 Local Storage Backend

```python
# app/media/storage/local.py

import os, shutil
from pathlib import Path

class LocalStorageBackend(StorageBackend):
    """
    Filesystem storage for local development.
    Serves files via /media/files/ Flask route.
    """

    def _get_base_path(self):
        from flask import current_app
        path = current_app.config.get('MEDIA_LOCAL_PATH', '/tmp/afcon360_media')
        Path(path).mkdir(parents=True, exist_ok=True)
        return path

    def save(self, file_obj, storage_key: str, content_type: str) -> str:
        base = self._get_base_path()
        full_path = os.path.join(base, storage_key)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'wb') as f:
            shutil.copyfileobj(file_obj, f)
        from flask import current_app
        prefix = current_app.config.get('MEDIA_LOCAL_URL_PREFIX', '/media/files')
        return f"{prefix}/{storage_key}"

    def delete(self, storage_key: str) -> bool:
        full_path = os.path.join(self._get_base_path(), storage_key)
        if os.path.exists(full_path):
            os.remove(full_path)
        return True

    def get_url(self, storage_key: str, expires_in: int = None) -> str:
        # Local dev: signed URL concept doesn't apply, just return path
        from flask import current_app
        prefix = current_app.config.get('MEDIA_LOCAL_URL_PREFIX', '/media/files')
        return f"{prefix}/{storage_key}"

    def exists(self, storage_key: str) -> bool:
        return os.path.exists(os.path.join(self._get_base_path(), storage_key))
```

### 6.4 Image Processor

```python
# app/media/processors/image.py

from PIL import Image
import io, hashlib

class ImageProcessor:
    """
    Optimize images to WebP with responsive size variants.
    Africa-first: aggressive compression, small file sizes.
    """

    SIZES = {
        'tiny':   (100, 100),
        'small':  (300, 225),
        'medium': (600, 450),
        'large':  (1024, 768),
        'original': None,
    }

    QUALITY = {
        'webp': 75,
        'jpeg': 82,
        'png':  85,
    }

    @classmethod
    def process(cls, file_obj, storage_key_prefix: str, backend) -> dict:
        """
        Generate all size variants in WebP.
        Returns dict of {size_name: url}.
        """
        img = Image.open(file_obj)

        # Convert HEIC/HEIF to RGB if needed
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGBA')
        else:
            img = img.convert('RGB')

        urls = {}

        for size_name, dimensions in cls.SIZES.items():
            variant = img.copy()
            if dimensions:
                variant.thumbnail(dimensions, Image.LANCZOS)

            buffer = io.BytesIO()
            variant.save(buffer, format='WEBP', quality=cls.QUALITY['webp'], method=6)
            buffer.seek(0)

            key = f"{storage_key_prefix}_{size_name}.webp"
            url = backend.save(buffer, key, 'image/webp')
            urls[size_name] = url

        return urls

    @classmethod
    def compute_hash(cls, file_obj) -> str:
        """SHA-256 hash for deduplication check."""
        file_obj.seek(0)
        h = hashlib.sha256()
        while chunk := file_obj.read(8192):
            h.update(chunk)
        file_obj.seek(0)
        return h.hexdigest()
```

### 6.5 Upload Validator

```python
# app/media/validators.py

ALLOWED_MAGIC_BYTES = {
    'image/jpeg': [b'\xff\xd8\xff'],
    'image/png':  [b'\x89PNG'],
    'image/webp': [b'RIFF'],
    'image/heic': [b'\x00\x00\x00'],  # ftyp box — needs secondary check
    'image/heif': [b'\x00\x00\x00'],
    'application/pdf': [b'%PDF'],
}

class UploadValidator:

    @classmethod
    def validate(cls, file, module: str, config: dict) -> tuple[bool, str]:
        """
        Validates: MIME type, magic bytes, file size.
        Returns (is_valid, error_message).
        """
        # 1. Size check
        file.seek(0, 2)
        size = file.tell()
        file.seek(0)
        max_size = config.get('max_size', 20 * 1024 * 1024)
        if size > max_size:
            return False, f"File too large. Max {max_size // (1024*1024)}MB allowed."

        # 2. MIME type check against module config
        allowed = config.get('allowed_types', [])
        if file.content_type not in allowed:
            return False, f"File type {file.content_type} not allowed for {module}."

        # 3. Magic bytes check (don't trust Content-Type header alone)
        header = file.read(12)
        file.seek(0)
        expected_magic = ALLOWED_MAGIC_BYTES.get(file.content_type, [])
        if expected_magic:
            if not any(header.startswith(magic) for magic in expected_magic):
                return False, "File content does not match declared type."

        return True, ""
```

### 6.6 Celery Task

```python
# app/media/tasks.py

from app.celery_app import celery
from app.extensions import db

@celery.task(bind=True, max_retries=3, default_retry_delay=30)
def process_media_task(self, media_id: int):
    """
    Async media processing task.
    Runs image optimization after upload.
    """
    from app.media.models import Media, MediaProcessingJob
    from app.media.processors.image import ImageProcessor
    from app.media.storage import get_storage_backend

    try:
        media = db.session.get(Media, media_id)
        if not media:
            return {'error': 'Media not found'}

        media.status = 'processing'
        db.session.commit()

        backend = get_storage_backend()

        if media.media_type == 'photo':
            # Re-fetch raw file from storage
            # storage_key points to the original upload
            raw_obj = backend.get_raw(media.storage_key)
            prefix = f"{media.module}/{media.entity_id}/{media.public_id}"
            urls = ImageProcessor.process(raw_obj, prefix, backend)

            media.urls = urls
            media.status = 'ready'

        elif media.media_type == 'video_url':
            # No processing needed — already stored as URL
            media.status = 'ready'
            media.urls = {'embed': f"https://www.youtube.com/embed/{media.video_url}"}

        db.session.commit()

        # Audit completion for KYC module
        if media.module == 'kyc':
            from app.audit.forensic_audit import ForensicAuditService
            ForensicAuditService.log_completion(
                audit_id=media.public_id,
                status='completed',
                result_details={'media_id': media.public_id, 'urls': media.urls}
            )

        return {'status': 'ready', 'urls': media.urls}

    except Exception as exc:
        media = db.session.get(Media, media_id)
        if media:
            media.status = 'failed'
            media.error_message = str(exc)
            db.session.commit()
        raise self.retry(exc=exc)
```

### 6.7 MediaService

```python
# app/media/service.py

import uuid as uuid_lib
from app.extensions import db
from app.audit.forensic_audit import ForensicAuditService
from flask import current_app

class MediaService:

    @classmethod
    def upload_photo(cls, file, module: str, entity_id: str,
                     uploader_user_id: int, caption: str = None,
                     is_cover: bool = False) -> dict:
        """
        Upload a photo for any module.
        entity_id MUST be a public UUID string (not BIGINT).
        uploader_user_id is the internal BIGINT (for DB FK only).
        Returns: {'media_id': str, 'status': 'processing', 'poll_url': str}
        """
        from app.media.models import Media
        from app.media.validators import UploadValidator
        from app.media.processors.image import ImageProcessor
        from app.media.storage import get_storage_backend
        from app.media.tasks import process_media_task

        module_config = current_app.config['MEDIA_MODULE_CONFIG'].get(module)
        if not module_config:
            raise ValueError(f"Unknown module: {module}")

        # Validate
        is_valid, error = UploadValidator.validate(file, module, module_config)
        if not is_valid:
            raise ValueError(error)

        # Deduplication check
        sha256 = ImageProcessor.compute_hash(file)
        existing = Media.query.filter_by(
            sha256_hash=sha256, module=module, is_deleted=False
        ).first()
        if existing:
            # Return existing record — same file already uploaded
            return {
                'media_id': existing.public_id,
                'status': existing.status,
                'urls': existing.urls,
                'deduplicated': True
            }

        # Save raw file to storage
        backend = get_storage_backend()
        raw_key = f"{module}/{entity_id}/raw/{sha256[:16]}_{file.filename}"
        backend.save(file, raw_key, file.content_type)

        # Create Media record
        public_id = str(uuid_lib.uuid4())
        media = Media(
            public_id=public_id,
            module=module,
            entity_id=entity_id,
            uploaded_by=uploader_user_id,
            media_type='photo',
            storage_key=raw_key,
            storage_backend=current_app.config.get('STORAGE_TYPE', 'local'),
            original_filename=file.filename,
            file_size=file.content_length,
            mime_type=file.content_type,
            sha256_hash=sha256,
            status='pending',
            caption=caption,
            is_cover=is_cover,
            is_public=module_config.get('is_public', True),
        )
        db.session.add(media)
        db.session.flush()  # Get media.id before task

        # Audit for KYC
        if module_config.get('audit_required'):
            ForensicAuditService.log_attempt(
                entity_type='media',
                entity_id=public_id,
                action='upload',
                user_id=uploader_user_id,
                details={'module': module, 'entity_id': entity_id, 'filename': file.filename}
            )

        # Queue async processing
        task = process_media_task.delay(media.id)
        db.session.commit()

        return {
            'media_id': public_id,
            'status': 'processing',
            'poll_url': f"/api/media/status/{public_id}",
            'celery_task_id': task.id
        }

    @classmethod
    def submit_youtube_url(cls, youtube_url: str, module: str,
                           entity_id: str, uploader_user_id: int,
                           caption: str = None) -> dict:
        """
        Register a YouTube video URL (no file storage).
        """
        from app.media.models import Media
        from app.media.processors.video import YouTubeURLValidator

        video_id = YouTubeURLValidator.extract_video_id(youtube_url)
        if not video_id:
            raise ValueError("Invalid YouTube URL. Must be youtube.com or youtu.be link.")

        public_id = str(uuid_lib.uuid4())
        media = Media(
            public_id=public_id,
            module=module,
            entity_id=entity_id,
            uploaded_by=uploader_user_id,
            media_type='video_url',
            video_url=video_id,
            storage_backend='none',
            status='ready',
            caption=caption,
            is_public=True,
            urls={
                'embed': f"https://www.youtube.com/embed/{video_id}",
                'thumbnail': f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg",
                'watch': f"https://www.youtube.com/watch?v={video_id}"
            }
        )
        db.session.add(media)
        db.session.commit()
        return {'media_id': public_id, 'status': 'ready', 'urls': media.urls}

    @classmethod
    def get_for_entity(cls, module: str, entity_id: str,
                       media_type: str = None) -> list:
        """Fetch all media for a module entity (e.g., all photos for a property)."""
        from app.media.models import Media
        q = Media.query.filter_by(
            module=module, entity_id=entity_id, is_deleted=False
        ).order_by(Media.is_cover.desc(), Media.display_order.asc())
        if media_type:
            q = q.filter_by(media_type=media_type)
        return q.all()

    @classmethod
    def delete(cls, media_public_id: str, requesting_user_id: int) -> bool:
        """Soft-delete a media record and remove from storage."""
        from app.media.models import Media
        from app.media.storage import get_storage_backend

        media = Media.query.filter_by(
            public_id=media_public_id, is_deleted=False
        ).first()
        if not media:
            return False

        # Delete from storage backend (best effort)
        if media.storage_key:
            try:
                get_storage_backend().delete(media.storage_key)
            except Exception:
                pass  # Log but don't fail

        media.soft_delete()  # BaseModel method
        db.session.commit()
        return True
```

### 6.8 API Routes

```python
# app/media/routes.py

from flask import Blueprint, request, jsonify, current_app, send_from_directory
from flask_login import login_required, current_user
from app.extensions import limiter

media_bp = Blueprint('media', __name__, url_prefix='/api/media')

@media_bp.route('/upload/<module>', methods=['POST'])
@login_required
@limiter.limit("50 per minute")
def upload(module: str):
    """
    Upload photo for a module.
    Requires: multipart/form-data with 'file' and 'entity_id' fields.
    Returns: 202 Accepted with media_id and poll URL.
    CSRF: Protected by Flask-WTF (POST method in WTF_CSRF_METHODS).
    """
    from app.media.service import MediaService

    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    entity_id = request.form.get('entity_id')
    caption = request.form.get('caption')
    is_cover = request.form.get('is_cover', 'false').lower() == 'true'

    if not entity_id:
        return jsonify({'error': 'entity_id required'}), 400

    try:
        result = MediaService.upload_photo(
            file=file,
            module=module,
            entity_id=entity_id,
            uploader_user_id=current_user.id,  # internal BIGINT
            caption=caption,
            is_cover=is_cover
        )
        return jsonify(result), 202
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        current_app.logger.exception(f"Media upload error: {e}")
        return jsonify({'error': 'Upload failed. Please try again.'}), 500


@media_bp.route('/youtube/<module>', methods=['POST'])
@login_required
@limiter.limit("20 per minute")
def submit_youtube(module: str):
    """Submit a YouTube URL for a module entity."""
    from app.media.service import MediaService
    data = request.get_json()
    if not data or 'youtube_url' not in data or 'entity_id' not in data:
        return jsonify({'error': 'youtube_url and entity_id required'}), 400

    try:
        result = MediaService.submit_youtube_url(
            youtube_url=data['youtube_url'],
            module=module,
            entity_id=data['entity_id'],
            uploader_user_id=current_user.id,
            caption=data.get('caption')
        )
        return jsonify(result), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@media_bp.route('/status/<media_public_id>', methods=['GET'])
@login_required
def status(media_public_id: str):
    """Poll processing status for a media item."""
    from app.media.models import Media
    media = Media.query.filter_by(
        public_id=media_public_id, is_deleted=False
    ).first()
    if not media:
        return jsonify({'error': 'Not found'}), 404
    return jsonify({
        'media_id': media.public_id,
        'status': media.status,
        'urls': media.urls,
        'error': media.error_message
    })


@media_bp.route('/entity/<module>/<entity_id>', methods=['GET'])
@login_required
def get_entity_media(module: str, entity_id: str):
    """Get all media for a module entity."""
    from app.media.service import MediaService
    items = MediaService.get_for_entity(module, entity_id)
    return jsonify([{
        'media_id': m.public_id,
        'media_type': m.media_type,
        'urls': m.urls,
        'caption': m.caption,
        'is_cover': m.is_cover,
        'display_order': m.display_order,
        'status': m.status
    } for m in items])


@media_bp.route('/delete/<media_public_id>', methods=['DELETE'])
@login_required
def delete(media_public_id: str):
    """Soft-delete a media item."""
    from app.media.service import MediaService
    success = MediaService.delete(media_public_id, current_user.id)
    if not success:
        return jsonify({'error': 'Not found or already deleted'}), 404
    return jsonify({'deleted': True})


@media_bp.route('/files/<path:filename>', methods=['GET'])
def serve_local_file(filename: str):
    """
    Serve local dev media files.
    In production (OCI), files are served directly from object storage.
    Only active when STORAGE_TYPE=local.
    """
    from flask import current_app, abort
    if current_app.config.get('STORAGE_TYPE') != 'local':
        abort(404)
    base = current_app.config.get('MEDIA_LOCAL_PATH', '/tmp/afcon360_media')
    return send_from_directory(base, filename)
```

### 6.9 YouTube URL Validator

```python
# app/media/processors/video.py

import re

class YouTubeURLValidator:
    """
    Validates and extracts YouTube video IDs.
    No video storage — YouTube is the CDN.
    """

    PATTERNS = [
        r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
        r'(?:https?://)?(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})',
        r'(?:https?://)?youtu\.be/([a-zA-Z0-9_-]{11})',
    ]

    @classmethod
    def extract_video_id(cls, url: str) -> str | None:
        """Extract YouTube video ID from URL. Returns None if invalid."""
        for pattern in cls.PATTERNS:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
```

---

## PART 7: FRONTEND COMPONENTS

### 7.1 JavaScript Media Manager
**File:** `static/js/global/media-manager.js`

Key requirements:
- Sends CSRF token on every POST: read from `<meta name="csrf-token" content="{{ raw_csrf_token }}">` in base.html
- Polls `/api/media/status/{media_id}` every 2 seconds until status=ready or failed
- Supports multiple file upload queue
- Shows upload progress bar
- Handles YouTube URL submission separately
- On completion: displays image thumbnail in gallery grid
- On failure: shows error message with retry option

CSRF injection into FormData:
```javascript
const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
formData.append('csrf_token', csrfToken);
// OR as header:
headers: { 'X-CSRFToken': csrfToken }
```

### 7.2 Template Component
**File:** `templates/components/media_upload.html`

Parameters (passed via Jinja2 context):
- `module` — module name string
- `entity_id` — the entity's PUBLIC UUID
- `existing_media` — list of Media objects already attached
- `allow_video` — bool, show YouTube URL input
- `max_files` — int, maximum uploads allowed

---

## PART 8: MODULE INTEGRATION — ACCOMMODATION FIRST

### 8.1 Changes to Accommodation Host Routes

File: `app/accommodation/routes/host_routes.py`

On property create/edit:
1. After property is saved, the form submits `media_ids[]` (list of Media public_ids already uploaded via the async uploader)
2. Route calls `MediaService.link_to_entity()` which sets `entity_id` on those Media records
3. Route queries `MediaService.get_for_entity('accommodation', property.public_id)` to populate `property.gallery` and `property.main_image`

On property display:
- Use `{{ media.urls.medium }}` for card thumbnails
- Use `{{ media.urls.large }}` for detail gallery
- Use `{{ media.urls.small }}` for mobile

### 8.2 Events Module Media Model Gap

Events currently stores images in `event_metadata` JSON. This needs a minimal fix:
- Add `event_banner_media_id` Column(String(64)) to Event model — stores a Media public_id
- No JSON, no URL columns — just the foreign reference to Media
- Migration required

---

## PART 9: SECURITY REQUIREMENTS

### 9.1 KYC Media (Highest Security Tier)

For `module='kyc'`:
- Files stored with private ACL (not public-read on OCI)
- `is_public=False` on Media record
- `get_url()` always called with `expires_in=3600` (signed URL, 1 hour)
- `ForensicAuditService.log_attempt()` before upload starts
- `ForensicAuditService.log_completion()` after Celery task succeeds
- `ForensicAuditService.log_blocked()` if validation fails
- KYC doc URLs never returned in public API responses

### 9.2 CSP Compliance

The existing CSP in `apply_security_headers` allows `img-src 'self' data: https:`. OCI Object Storage URLs (https://namespace.compat.objectstorage.region.oraclecloud.com) fall under `https:` — this is already allowed. No CSP changes needed for photos.

For the media-manager.js script: it must be served with the per-request nonce via `<script nonce="{{ csp_nonce }}">` tag, consistent with all other scripts in the app.

### 9.3 Rate Limiting

Upload endpoint: `50 per minute` per user (via Flask-Limiter, backed by Redis).
YouTube submission: `20 per minute`.
Status polling: `120 per minute` (frequent polling expected).

---

## PART 10: DEPENDENCIES

### New Python Packages Required

```
Pillow>=10.0.0          # Image processing (WebP/AVIF)
boto3>=1.34.0           # OCI S3-compatible client
botocore>=1.34.0        # Required by boto3
```

Add to `requirements.txt`. Both are lightweight and work on ARM (Oracle Ampere).

**Note on AVIF:** AVIF support in Pillow requires `pillow-avif-plugin` or Pillow 10+ with libavif compiled in. On Oracle Linux / Ubuntu on ARM, libavif may need manual installation. Start with WebP only (excellent compression, universal support) and add AVIF later.

---

## PART 11: MIGRATION

```python
# migrations/versions/add_media_tables.py

def upgrade():
    # Create media table
    op.create_table(
        'media',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('public_id', sa.String(64), nullable=False),
        sa.Column('module', sa.String(50), nullable=False),
        sa.Column('entity_id', sa.String(64), nullable=False),  # PUBLIC UUID — not BIGINT
        sa.Column('uploaded_by', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('media_type', sa.Enum('photo', 'document', 'video_url', name='media_type_enum'), nullable=False),
        sa.Column('storage_key', sa.String(500), nullable=True),
        sa.Column('storage_backend', sa.String(20), nullable=False, server_default='local'),
        sa.Column('video_url', sa.String(500), nullable=True),
        sa.Column('original_filename', sa.String(255), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('mime_type', sa.String(100), nullable=True),
        sa.Column('sha256_hash', sa.String(64), nullable=True),
        sa.Column('status', sa.Enum('pending', 'processing', 'ready', 'failed', name='media_status_enum'), nullable=False, server_default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('urls', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('caption', sa.String(300), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_cover', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('public_id', name='uq_media_public_id'),
        sa.Index('ix_media_module_entity', 'module', 'entity_id'),
        sa.Index('ix_media_status', 'status'),
        sa.Index('ix_media_sha256', 'sha256_hash'),
        sa.Index('ix_media_is_deleted', 'is_deleted'),
    )

    # Create media_processing_jobs table
    op.create_table(
        'media_processing_jobs',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('public_id', sa.String(64), nullable=False),
        sa.Column('media_id', sa.BigInteger(), sa.ForeignKey('media.id', ondelete='CASCADE'), nullable=False),
        sa.Column('celery_task_id', sa.String(64), nullable=True),
        sa.Column('job_type', sa.String(50), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='queued'),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('ix_mpj_celery_task', 'celery_task_id'),
        sa.Index('ix_mpj_media_id', 'media_id'),
    )


def downgrade():
    op.drop_table('media_processing_jobs')
    op.execute("DROP TYPE IF EXISTS media_status_enum")
    op.execute("DROP TYPE IF EXISTS media_type_enum")
    op.drop_table('media')
```

---

## PART 12: BLUEPRINT REGISTRATION

Add to `app/__init__.py` in `create_app()`, alongside other blueprints:

```python
# In the api blueprints section:
from app.media.routes import media_bp
app.register_blueprint(media_bp)
```

Also register the local file serving route only when `STORAGE_TYPE=local` — this is handled automatically in the route itself (returns 404 if not local).

---

## PART 13: KNOWN CONFLICTS TO RESOLVE

| Conflict | Location | Resolution |
|----------|----------|------------|
| `verified_by` column vs relationship name in KycRecord | `app/kyc/models.py` line ~65 | Rename relationship to `verified_by_user` — flag for Kilo but do NOT fix in this chain |
| `KycRecord.user_id` is BIGINT FK but `MediaService` needs `entity_id` as public UUID | `app/kyc/models.py` | Use `kyc_record.reference_code` or `kyc_record.id` as entity_id for KYC media. Confirm with Chief Product Engineer before implementing KYC media integration |
| Events `event_metadata` JSON holds image URLs | `app/events/models.py` | Add `event_banner_media_id = Column(String(64))` in separate migration — flag before executing |
| Accommodation `PropertyPhoto` model already exists with `storage_key` column | `app/accommodation/models/property.py` | Media module does NOT replace PropertyPhoto immediately. Phase 1: parallel coexistence. Phase 2: migrate. Flag in report. |

---

---

# KILO AGENT EXECUTION BRIEF
## Orchestration, Implementation, Verification & Report

---

## REPORT FILE LOCATION

> **Kilo writes ALL implementation reports to:**
> `reports/media_system_implementation_report.md`
>
> Do NOT edit this master document to record progress.
> The master document is read-only for Kilo.
> The report file is the only file Kilo writes to for status, conflicts, deviations, and final sign-off.
> The report file already exists with the correct template — open it and fill it in.

---

## KILO ROLE DEFINITIONS

| Role | Responsibility |
|------|---------------|
| **Orchestrator** | Reads this document, decomposes into chains, assigns roles, tracks progress |
| **Planner** | For each phase, creates a specific task list with file paths and line numbers |
| **Agent** | Writes the actual code, runs migrations, updates config |
| **Inspector** | Reviews every file written against the rules in this document |
| **Verifier** | Runs checks (imports, syntax, test if available), confirms no regressions |
| **Reporter** | Updates `reports/media_system_implementation_report.md` after each phase |

---

## EXECUTION PHASES

### PHASE 0 — Pre-flight Checks (Orchestrator + Inspector)
Before writing any code:

- [ ] Confirm `app/celery_app.py` exists and `celery` instance is importable
- [ ] Confirm `app/audit/forensic_audit.py` exists (✅ provided — confirmed)
- [ ] Confirm `app/models/base.py` has `BaseModel` with `is_deleted`, `created_at`, `updated_at` (✅ confirmed)
- [ ] Confirm `app/extensions.py` exports `db`, `limiter`, `cache`
- [ ] Confirm `requirements.txt` exists at project root
- [ ] Check if `Pillow` is already in `requirements.txt`
- [ ] Check if `boto3` is already in `requirements.txt`
- [ ] Confirm `MEDIA_MODULE_CONFIG` does NOT already exist in `app/config.py`
- [ ] Confirm no existing `app/media/` directory (would be overwritten)
- [ ] Confirm `app/accommodation/models/property.py` has `PropertyPhoto` model — note it, do NOT remove it
- [ ] Read `app/__init__.py` lines around blueprint registration to find correct insertion point

**If any check fails or reveals a conflict → STOP and add to Conflicts section of report. Do not proceed past Phase 0 until all checks pass or conflicts are documented.**

---

### PHASE 1 — Dependencies & Config (Agent)

**Task 1.1 — Add to `requirements.txt`:**
```
Pillow>=10.0.0
boto3>=1.34.0
botocore>=1.34.0
```
Only add if not already present.

**Task 1.2 — Add to `app/config.py` inside `class Config:`**
Add all variables from Part 5.1 of this document.
Insertion point: after the `AUDIT` dict block, before `validate_for_production()`.

**Inspector check after Phase 1:**
- [ ] `Config.STORAGE_TYPE` reads from env with default `'local'`
- [ ] `Config.MEDIA_MODULE_CONFIG` is a dict with at least `accommodation`, `user`, `kyc` keys
- [ ] No existing config keys overwritten
- [ ] `requirements.txt` has exactly one entry for Pillow and boto3 (no duplicates)

---

### PHASE 2 — Core Module Structure (Agent)

Create the following files in order:

1. `app/media/__init__.py` — empty init, just blueprint import
2. `app/media/storage/__init__.py` — `StorageBackend` base class + `get_storage_backend()` factory
3. `app/media/storage/local.py` — `LocalStorageBackend`
4. `app/media/storage/oci.py` — `OCIStorageBackend`
5. `app/media/validators.py` — `UploadValidator`
6. `app/media/processors/__init__.py` — empty
7. `app/media/processors/image.py` — `ImageProcessor`
8. `app/media/processors/video.py` — `YouTubeURLValidator`
9. `app/media/models.py` — `Media` + `MediaProcessingJob` extending `BaseModel`
10. `app/media/service.py` — `MediaService`
11. `app/media/tasks.py` — `process_media_task` Celery task
12. `app/media/routes.py` — `media_bp` Flask blueprint

**Inspector check after Phase 2:**
- [ ] Every model extends `BaseModel` from `app.models.base`
- [ ] No model manually defines `id`, `is_deleted`, `created_at`, `updated_at` — inherited
- [ ] `entity_id` column is `String(64)` NOT `BigInteger` in Media model
- [ ] `uploaded_by` column is `BigInteger` (internal FK to users.id) — never exposed in API responses
- [ ] `Media.public_id` is the external identifier in all API responses
- [ ] `get_storage_backend()` uses `current_app.config` not module-level globals
- [ ] `process_media_task` uses `db.session.get(Media, media_id)` not `Media.query.get()`
- [ ] `UploadValidator` checks magic bytes, not just MIME type
- [ ] `YouTubeURLValidator` rejects non-YouTube URLs
- [ ] `MediaService.upload_photo()` calls `ForensicAuditService.log_attempt()` for KYC module
- [ ] No circular imports — all model imports inside functions where possible

---

### PHASE 3 — Database Migration (Agent + Verifier)

Create `migrations/versions/add_media_tables.py` using the migration spec in Part 11.

**Agent:** Use `flask db migrate` if possible, or write the migration manually from the spec.

**Verifier checks:**
- [ ] `entity_id` column type is `String(64)` in migration — NOT BigInteger
- [ ] `media_type_enum` and `media_status_enum` PostgreSQL enums created with `op.execute()` before `op.create_table()`
- [ ] `downgrade()` drops both tables AND the enum types
- [ ] No `sa.inspect()` calls (not needed in this migration)
- [ ] Run `flask db upgrade` — confirm it applies without error
- [ ] Run `flask db downgrade` — confirm rollback works
- [ ] Run `flask db upgrade` again — confirm idempotent

---

### PHASE 4 — Blueprint Registration (Agent)

In `app/__init__.py`:
1. Find the API blueprints import block (look for `wallet_api_bp`, `fx_api_bp`)
2. Add: `from app.media.routes import media_bp`
3. Find the `api_blueprints = [...]` list
4. Add `media_bp` to the list

**Inspector check:**
- [ ] No duplicate registration of `media_bp`
- [ ] `media_bp` uses prefix `/api/media` — confirm this doesn't clash with any existing route
- [ ] Local file serving route `/media/files/<path>` is registered — accessible in local dev

---

### PHASE 5 — Frontend Components (Agent)

**5.1** Create `templates/components/media_upload.html`
- Must include CSRF token meta consumption from `{{ raw_csrf_token }}`
- Accept `module`, `entity_id`, `existing_media`, `allow_video`, `max_files` as template variables
- YouTube URL input section (shown when `allow_video=True`)
- Upload progress bar
- Gallery grid for existing + newly uploaded media

**5.2** Create `templates/components/media_gallery.html`
- Displays list of Media objects
- Uses `{{ media.urls.medium }}` for display
- Shows cover badge on `is_cover=True` items

**5.3** Create `static/js/global/media-manager.js`
- Reads CSRF token from `<meta name="csrf-token">`
- Sends CSRF token in all POST/DELETE requests
- Polls `/api/media/status/{media_id}` every 2 seconds until ready
- Uses `nonce="{{ csp_nonce }}"` attribute on script tag in templates

**5.4** Create `static/css/modules/media.css`
- Drop zone styles
- Progress bar styles
- Gallery grid styles

**Inspector check:**
- [ ] JS file does NOT use `localStorage` or `sessionStorage`
- [ ] CSRF token is sent in upload request
- [ ] Polling stops on `status=ready` OR `status=failed`
- [ ] No hardcoded URLs in JS — all API paths are configurable
- [ ] Script tag uses `nonce` attribute in template that includes the component

---

### PHASE 6 — Accommodation Integration (Agent)

**6.1** In `app/accommodation/routes/host_routes.py`:
- Import `MediaService` from `app.media.service`
- On property create: after saving `prop`, call `MediaService.get_for_entity('accommodation', prop.public_id)` and populate `prop.main_image` from cover photo
- On property create form: include `{% include 'components/media_upload.html' %}` with `module='accommodation'`, `entity_id=property.public_id`, `allow_video=True`

**6.2** In accommodation property detail templates:
- Replace raw `property.main_image` URL with `{{ property.main_image }}` (unchanged — MediaService writes back to this column)
- Add gallery section using `media_gallery.html` component

**Inspector check:**
- [ ] `entity_id` passed to MediaService is `property.public_id` (UUID string) — NOT `property.id`
- [ ] `uploader_user_id` passed is `current_user.id` (internal BIGINT) — NOT `current_user.public_id`
- [ ] YouTube URL input is present in the accommodation host form
- [ ] No direct `request.files` handling in accommodation routes — all delegated to MediaService

---

### PHASE 7 — Final Verification (Verifier)

**7.1 Import verification:**
```bash
cd /project/root
python -c "from app.media.models import Media, MediaProcessingJob; print('Models OK')"
python -c "from app.media.service import MediaService; print('Service OK')"
python -c "from app.media.routes import media_bp; print('Blueprint OK')"
python -c "from app.media.storage import get_storage_backend; print('Storage OK')"
python -c "from app.media.tasks import process_media_task; print('Tasks OK')"
```

**7.2 Config verification:**
```bash
python -c "from app.config import Config; assert hasattr(Config, 'STORAGE_TYPE'); assert hasattr(Config, 'MEDIA_MODULE_CONFIG'); print('Config OK')"
```

**7.3 Migration verification:**
```bash
flask db upgrade
flask db downgrade
flask db upgrade
```

**7.4 Route verification:**
```bash
flask routes | grep media
# Expected: at least 5 media routes visible
```

**7.5 Storage backend switching verification:**
```bash
STORAGE_TYPE=local python -c "
from app import create_app
app = create_app()
with app.app_context():
    from app.media.storage import get_storage_backend
    b = get_storage_backend()
    print(type(b).__name__)  # Expected: LocalStorageBackend
"

STORAGE_TYPE=oci python -c "
from app import create_app
app = create_app()
with app.app_context():
    from app.media.storage import get_storage_backend
    b = get_storage_backend()
    print(type(b).__name__)  # Expected: OCIStorageBackend
"
```

---

## RULES KILO MUST NEVER VIOLATE

1. **Never expose `user.id` (BIGINT) in API responses.** Use `user.public_id` for all external output.
2. **Never use `BigInteger` for `entity_id` in the Media model.** It is always `String(64)` UUID.
3. **Never handle file I/O synchronously in Flask routes.** Save raw file to storage, then defer to Celery.
4. **Never call `db.session.commit()` inside a Celery task without a try/except rollback.**
5. **Never skip ForensicAuditService for `module='kyc'` operations.**
6. **Never add `is_deleted`, `created_at`, `updated_at`, `id` to models that extend `BaseModel`.** These are inherited.
7. **Never register `media_bp` more than once in `create_app()`.**
8. **Never use `localStorage` or `sessionStorage` in JS (Claude.ai CSP policy).**
9. **Never accept a YouTube URL and serve it without extracting the video ID first.**
10. **Never skip the magic bytes check in UploadValidator.** MIME type headers are user-controlled and untrustworthy.

---

*Master document ends here. Kilo writes all implementation progress to `reports/media_system_implementation_report.md`*
