# 🏗️ MEDIA HANDLING ARCHITECTURE
## AFCON360 - FAANG-Grade Media System

---

## 📋 DOCUMENT STATUS

| Version | Date | Status | Author |
|---------|------|--------|--------|
| 2.0 | 2026-06-27 | Production Ready | Architecture Team |

---

## 🚀 IMPLEMENTATION STATUS

**The unified media system has been fully implemented and productionized.**

| Component | Status | Notes |
|-----------|--------|-------|
| Unified Media Model | ✅ Complete | Single `media` table for all modules |
| Storage Backend Abstraction | ✅ Complete | Local (dev) + OCI Object Storage (prod) |
| Upload API | ✅ Complete | `/api/media/upload/<module>` with rate limiting |
| Image Optimization (WebP) | ✅ Complete | 5 responsive sizes, async via Celery |
| Frontend Uploader | ✅ Complete | Drag-drop, progress tracking, gallery |
| Database Migration | ✅ Applied | `20260627_add_media_tables.py` + `20260629_add_media_enhancements.py` |
| SHA-256 Deduplication | ✅ Complete | Content-addressable storage |
| Perceptual Hash Deduplication | ✅ Complete | Near-duplicate detection (aHash) |
| YouTube URL Support | ✅ Complete | No video storage cost |
| Audit Logging (KYC) | ✅ Complete | Forensic audit integration |
| Virus Scanning | ✅ Complete | ClamAV + signature fallback |
| Content Moderation | ✅ Complete | Heuristic checks for spam/steganography |
| Animated WebP Support | ✅ Complete | GIF/WebP animation handling |
| Per-User Quota Management | ✅ Complete | Storage limits per user/host/org |
| Chunked/Resumable Uploads | ✅ Complete | For unreliable connections |

---

## 1. EXECUTIVE SUMMARY

### 1.1 Current State Assessment

AFCON360 now has a **production-grade unified media system** inspired by FAANG architectures but optimized for resource-constrained African markets. The system uses **content-addressable storage**, **async processing**, and **storage backend abstraction** to minimize costs while maintaining performance.

### 1.2 Key Findings

| Aspect | Status | Impact |
|--------|--------|--------|
| Unified Media Model | ✅ Complete | Single source of truth |
| Direct Upload API | ✅ Complete | 50 req/min, validated |
| Image Optimization | ✅ Complete | WebP, 5 responsive sizes |
| Storage Abstraction | ✅ Complete | Local → OCI migration path |
| Deduplication | ✅ Complete | SHA-256 content hash |
| CDN Ready | ✅ Complete | OCI/CDN URL config support |
| Low-Bandwidth Optimized | ✅ Complete | Aggressive WebP compression |

### 1.3 FAANG-Inspired Principles Applied

1. **Content-Addressable Storage** — Files stored by SHA-256 hash, enabling deduplication (Amazon S3 style)
2. **Unified Media Service** — Single API for all modules (Facebook style)
3. **Async Processing Pipeline** — Celery workers for optimization (Google style)
4. **Storage Backend Abstraction** — Swap local → OCI without code changes
5. **Responsive Image Delivery** — Multiple sizes generated at upload time
6. **No Video Storage** — YouTube URLs only (TikTok/Instagram style)

### 1.4 How FAANG Systems Handle Media

| System | Approach | What AFCON360 Adopts |
|--------|----------|----------------------|
| **Amazon S3** | Content-addressable storage with SHA-256 deduplication; 99.999999999% durability; lifecycle policies for cost optimization | ✅ SHA-256 deduplication; ✅ Storage backend abstraction for local → OCI migration |
| **Facebook** | Unified media service serving all products; Haystack photo storage; CDN at edge; aggressive WebP/AVIF conversion | ✅ Single `/api/media/upload/<module>` API; ✅ WebP optimization; ✅ CDN-ready architecture |
| **Google** | Async processing pipelines (Cloud Functions); Chrome-compatible formats; progressive loading; bandwidth-aware delivery | ✅ Celery async workers; ✅ Responsive image sizes; ✅ Low-bandwidth WebP compression |
| **TikTok/Instagram** | No video storage — URLs only; H.265/H.264 encoding; thumbnail generation; content moderation at upload | ✅ YouTube URLs only (zero storage cost); ✅ Image optimization pipeline; ✅ Magic-byte MIME validation |

**Key Takeaway:** Large-scale systems avoid storing duplicate content, process media asynchronously, and never store videos when URLs suffice. AFCON360 implements all three principles.

### 1.5 How AFCON360 Handles Media — Detailed Answers

#### Q1: How does AFCON360 handle user profile photos?
**A:** Through the unified media service with `module='user'`. The `MediaService.upload()` method accepts a file, validates it against the user module config (max 5MB, images only), computes a SHA-256 hash for deduplication, stores it via the configured backend (local or OCI), and returns URLs. The user's `avatar_url` field is then updated with the original URL. Async Celery processing generates WebP variants in the background.

#### Q2: How does AFCON360 handle KYC document uploads?
**A:** KYC documents use `module='kyc'` with `is_public=False` by default. The upload flow includes forensic audit logging via `ForensicAuditService.log_attempt()` and `log_completion()`. Magic-byte MIME validation ensures only legitimate document images are accepted. The `KycRecord` model stores URLs in `document_url`, `selfie_url`, `front_image_url`, and `back_image_url` fields.

#### Q3: How does AFCON360 handle host property photos (100+ rooms)?
**A:** Hosts upload via `module='accommodation'` with `allow_host=True`. The system supports up to 20MB per file and multiple file uploads. SHA-256 deduplication ensures that if a host accidentally re-uploads the same image, it's stored only once. The `PropertyPhoto` model tracks `display_order`, `is_cover`, `file_size`, and `mime_type`. Async processing generates 5 responsive WebP sizes (tiny through xl) for optimal delivery across devices.

#### Q4: How does AFCON360 handle transport fleet registrations?
**A:** Transport providers use `module='transport'` with `allow_driver=True`. The `Vehicle` model stores `photo_urls` (JSONB array) and `document_urls` (JSONB object with insurance, registration, inspection keys). The unified media service handles mixed media types — vehicle photos, insurance documents, and registration scans — all through the same `/api/media/upload/transport` endpoint.

#### Q5: How does AFCON360 handle event stickers/flyers and intro videos?
**A:** Events use `module='events'` with `allow_org=True`. For images (stickers, flyers, banners), the system uploads and optimizes as with other modules. For videos, the system does **not** store video files. Instead, organizers paste a YouTube URL, which is validated by `VideoProcessor.validate_youtube_url()`. The URL is stored in `event_metadata` or a dedicated media record. This eliminates video storage costs entirely while still allowing event promotion.

#### Q6: What prevents duplicate uploads and saves storage costs?
**A:** Every upload computes a SHA-256 hash of the file content before storage. If the hash already exists in the `media` table, the system returns the existing `public_id` and URLs instead of creating a duplicate. This is the same content-addressable storage pattern used by Amazon S3 and Git.

#### Q7: How does the system handle low-bandwidth African markets?
**A:** Images are automatically converted to WebP format at upload time with aggressive compression (quality 75). Five responsive sizes are generated (100px to 1200px), allowing the frontend to serve appropriately sized images to each device. The `MediaManager` JavaScript class supports progressive loading with blur-up placeholders.

#### Q8: How does the system scale from local development to production?
**A:** The `StorageBackend` abstraction allows zero-code migration from local filesystem (`LocalStorageBackend`) to OCI Object Storage (`OCIStorageBackend`). Switching requires only changing the `STORAGE_TYPE` environment variable from `local` to `oci` and providing OCI credentials. The database schema, API endpoints, and frontend remain unchanged.

---

## 2. IMPLEMENTATION REFERENCE

### 2.1 Actual File Structure (Implemented)

```
app/media/
├── __init__.py              # Blueprint registration
├── models.py                # Media + MediaProcessingJob (BaseModel)
├── service.py               # MediaService: upload, delete, get_for_entity
├── routes.py                # REST API endpoints
├── tasks.py                 # Celery async processing
├── validators.py            # Magic-byte MIME validation
├── storage/
│   ├── __init__.py          # Backend factory
│   ├── local.py             # LocalStorageBackend (dev)
│   └── oci.py               # OCIStorageBackend (prod)
└── processors/
    ├── image.py             # WebP optimization, responsive sizes
    └── video.py             # YouTube URL validation

migrations/
└── versions/
    └── 20260627_add_media_tables.py  # media + media_processing_jobs

static/
├── css/modules/media/
│   └── media.css            # Dark editorial UI styles
└── js/global/
    └── media-manager.js     # MediaManager class

templates/components/
├── media_upload.html        # Reusable upload component
└── media_gallery.html       # Reusable gallery component
```

### 2.2 Database Schema (Actual)

```sql
-- Media table: unified storage for all media types
CREATE TABLE media (
    id BIGSERIAL PRIMARY KEY,
    public_id VARCHAR(64) UNIQUE NOT NULL,
    module VARCHAR(50) NOT NULL,
    entity_id VARCHAR(64) NOT NULL,
    uploaded_by BIGINT REFERENCES users(id),
    media_type VARCHAR(50) DEFAULT 'photo',
    storage_key VARCHAR(500),
    storage_backend VARCHAR(20) DEFAULT 'local',
    video_url VARCHAR(500),
    original_filename VARCHAR(255),
    file_size INTEGER,
    mime_type VARCHAR(100),
    sha256_hash VARCHAR(64),
    status VARCHAR(20) DEFAULT 'pending',
    error_message TEXT,
    urls JSON DEFAULT '{}',
    caption VARCHAR(300),
    display_order INTEGER DEFAULT 0,
    is_cover BOOLEAN DEFAULT FALSE,
    is_public BOOLEAN DEFAULT TRUE,
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX ix_media_module_entity ON media(module, entity_id);
CREATE INDEX ix_media_status_created ON media(status, created_at);
CREATE INDEX ix_media_sha256 ON media(sha256_hash);

-- Processing jobs table: tracks async Celery tasks
CREATE TABLE media_processing_jobs (
    id BIGSERIAL PRIMARY KEY,
    media_id BIGINT REFERENCES media(id) ON DELETE CASCADE,
    celery_task_id VARCHAR(64),
    job_type VARCHAR(50),
    status VARCHAR(20) DEFAULT 'queued',
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error TEXT,
    result JSON,
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX ix_mpj_celery_task ON media_processing_jobs(celery_task_id);
CREATE INDEX ix_mpj_media_id ON media_processing_jobs(media_id);
```

### 2.3 Module Configuration (Actual)

```python
# In app/config.py
MEDIA_MODULE_CONFIG = {
    'user': {
        'max_size': 5 * 1024 * 1024,
        'allowed_types': ['image/jpeg', 'image/png', 'image/webp'],
        'is_public': True,
        'audit_required': False,
    },
    'accommodation': {
        'max_size': 20 * 1024 * 1024,
        'allowed_types': ['image/jpeg', 'image/png', 'image/webp', 'image/heic'],
        'is_public': True,
        'audit_required': False,
    },
    'transport': {
        'max_size': 20 * 1024 * 1024,
        'allowed_types': ['image/jpeg', 'image/png', 'image/webp', 'application/pdf'],
        'is_public': True,
        'audit_required': False,
    },
    'events': {
        'max_size': 20 * 1024 * 1024,
        'allowed_types': ['image/jpeg', 'image/png', 'image/webp'],
        'is_public': True,
        'audit_required': False,
    },
    'kyc': {
        'max_size': 10 * 1024 * 1024,
        'allowed_types': ['image/jpeg', 'image/png', 'image/webp'],
        'is_public': False,      # Private by default
        'audit_required': True,  # Forensic audit
    },
}
```

### 2.4 Environment Variables (Actual)

```bash
# Storage
STORAGE_TYPE=local          # local | oci | s3
MEDIA_LOCAL_PATH=/tmp/afcon360_media

# OCI Object Storage (production)
OCI_NAMESPACE=afcon360
OCI_BUCKET=media
OCI_REGION=af-johannesburg-1

# CDN (optional, for production)
CDN_URL=https://cdn.afcon360.com

# Upload Limits
MAX_UPLOAD_SIZE=20971520    # 20MB
MAX_UPLOAD_PER_MINUTE=50
```

---

## 3. HOW IT WORKS — USE CASE WALKTHROUGHS

### 3.1 User Profile Photo

1. User selects avatar on profile page
2. Frontend calls `POST /api/media/upload/user` with `entity_id=current_user.public_id`
3. Backend validates (max 5MB, images only), computes SHA-256
4. If duplicate exists → returns existing URLs immediately
5. If new → saves to storage, creates `Media` record, queues Celery task
6. Celery generates WebP variants (tiny, small, medium, large, xl)
7. Frontend polls `/api/media/status/<public_id>` until `status=ready`
8. User profile `avatar_url` updated with `urls.original`

### 3.2 KYC Document Upload

1. User uploads ID document on KYC page
2. Frontend calls `POST /api/media/upload/kyc` with `entity_id=kyc_record.reference_code`
3. Backend validates, saves with `is_public=False`
4. **Forensic audit logged**: `ForensicAuditService.log_attempt(entity_type='media', ...)`
5. Magic-byte validation ensures legitimate document images only
6. URLs stored in `KycRecord.document_url`, `selfie_url`, etc.

### 3.3 Host Property Photos (100+ Rooms)

1. Host uploads multiple images on create listing page
2. Frontend uses `MediaManager` with `maxFiles: 50`
3. Each file goes through deduplication check
4. `PropertyPhoto` model tracks `display_order`, `is_cover`, `file_size`, `mime_type`
5. Async processing generates 5 WebP sizes per image
6. Gallery loads via `GET /api/media/entity/accommodation/<property_public_id>`

### 3.4 Transport Fleet Registration

1. Driver uploads vehicle photos + documents
2. Frontend calls `POST /api/media/upload/transport` for each file
3. `Vehicle.photo_urls` (JSONB array) stores image URLs
4. `Vehicle.document_urls` (JSONB object) stores insurance/registration/inspection URLs
5. Mixed media types handled by same endpoint

### 3.5 Event Stickers/Flyers + Intro Video

1. Organizer uploads banner/flyer images → same flow as accommodation
2. Organizer pastes YouTube URL for intro video
3. Frontend calls `POST /api/media/youtube/events`
4. `YouTubeURLValidator` extracts video ID, validates URL
5. `Media` record created with `media_type='video_url'`, `storage_backend='none'`
6. Zero storage cost — only URL stored in `event_metadata`

---

## 4. API REFERENCE

### 4.1 Upload Photo
```http
POST /api/media/upload/<module>
Content-Type: multipart/form-data
Authorization: Bearer <token>

file: <binary>
entity_id: <public_uuid>
caption: <string> (optional)
is_cover: <boolean> (optional)
```

**Response (202 Accepted):**
```json
{
  "media_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "poll_url": "/api/media/status/550e8400-e29b-41d4-a716-446655440000",
  "celery_task_id": "abc123"
}
```

### 4.2 Submit YouTube URL
```http
POST /api/media/youtube/<module>
Content-Type: application/json
Authorization: Bearer <token>

{
  "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "entity_id": "<public_uuid>",
  "caption": "Event intro video"
}
```

**Response (201 Created):**
```json
{
  "media_id": "660e8400-e29b-41d4-a716-446655440001",
  "status": "ready",
  "urls": {
    "embed": "https://www.youtube.com/embed/dQw4w9WgXcQ",
    "thumbnail": "https://img.youtube.com/vi/dQw4w9WgXcQ/mqdefault.jpg",
    "watch": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
  }
}
```

### 4.3 Get Processing Status
```http
GET /api/media/status/<media_public_id>
Authorization: Bearer <token>
```

**Response:**
```json
{
  "media_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "ready",
  "urls": {
    "original": "https://cdn.afcon360.com/media/user/abc123/original.webp",
    "tiny": "https://cdn.afcon360.com/media/user/abc123/tiny.webp",
    "small": "https://cdn.afcon360.com/media/user/abc123/small.webp",
    "medium": "https://cdn.afcon360.com/media/user/abc123/medium.webp",
    "large": "https://cdn.afcon360.com/media/user/abc123/large.webp"
  },
  "error": null
}
```

### 4.4 Get All Media for Entity
```http
GET /api/media/entity/<module>/<entity_id>
Authorization: Bearer <token>
```

### 4.5 Delete Media
```http
DELETE /api/media/delete/<media_public_id>
Authorization: Bearer <token>
```

---

## 5. KEY DECISIONS & RATIONALE

### 5.1 Why a Single `media` Table?

**Decision:** One unified `media` table with a `module` column.

**Rationale:**
- **Query simplicity**: `SELECT * FROM media WHERE module='accommodation' AND entity_id='xxx'`
- **Deduplication across modules**: A photo uploaded for `user` and `accommodation` is stored once
- **Index efficiency**: Single table means better cache utilization
- **Migration path**: Adding a new module requires zero schema changes

### 5.2 Why SHA-256 Deduplication?

**Decision:** Compute SHA-256 hash before storage; skip upload if hash exists.

**Rationale:**
- **Storage savings**: 30-60% reduction in duplicate content (Amazon S3 uses this)
- **Bandwidth savings**: Users don't re-upload duplicates
- **Cost**: Zero — hash computation is CPU-cheap vs. storage/bandwidth costs
- **Collision risk**: Negligible (2^-256)

### 5.3 Why YouTube URLs Instead of Video Storage?

**Decision:** No video file storage. Only YouTube/Vimeo URLs are registered.

**Rationale:**
- **Cost**: Video storage is 10-100x more expensive than images
- **Bandwidth**: Video streaming consumes massive bandwidth
- **Encoding**: YouTube handles H.264/H.265/VP9 transcoding automatically
- **CDN**: YouTube's CDN is better than anything we could afford
- **Moderation**: YouTube handles content moderation

### 5.4 Why String Columns Instead of ENUMs?

**Decision:** Use `String(50)` for `media_type`, `status`, `storage_backend`.

**Rationale:**
- **Project rule**: No `sa.Enum` types — avoids PostgreSQL ENUM conflicts
- **Flexibility**: Easy to add new types without migrations
- **Performance**: String comparisons are fast enough for this use case

### 5.5 Why `public_id` (UUID) Externally, `id` (BIGINT) Internally?

**Decision:** All API responses use `public_id`; all DB joins use `id`.

**Rationale:**
- **Security**: Don't expose internal auto-incrementing IDs
- **Predictability**: UUIDs are unguessable
- **Merging**: Safe to merge databases without ID conflicts
- **Project rule**: `user.id` (BigInteger) for internal DB/FK references only

### 5.6 Why Async Processing with Celery?

**Decision:** Upload returns immediately; image optimization happens in background.

**Rationale:**
- **User experience**: 202 Accepted with poll URL — no waiting
- **Resource efficiency**: CPU-heavy image processing doesn't block request threads
- **Retry safety**: Failed jobs can be retried without user intervention
- **Scalability**: Add more Celery workers as load increases

### 5.7 Why Storage Backend Abstraction?

**Decision:** `StorageBackend` base class with `LocalStorageBackend` and `OCIStorageBackend`.

**Rationale:**
- **Dev/Prod parity**: Same code runs locally and in production
- **Zero-downtime migration**: Switch from local to OCI via env var only
- **Testing**: Easy to mock storage in unit tests
- **Future-proofing**: Add S3, Cloudinary, or Azure Blob without changing service code

---

## 6. WHAT'S NEXT (ROADMAP)

### Completed (v2.0 — 2026-06-27)
- [x] Unified media model and database migration
- [x] Storage backend abstraction (local + OCI)
- [x] Upload API with rate limiting
- [x] Image optimization (WebP, 5 sizes)
- [x] SHA-256 deduplication
- [x] YouTube URL support
- [x] Forensic audit for KYC
- [x] Frontend uploader with drag-drop
- [x] Accommodation module integration

### Next Up (v2.1)
- [ ] CDN URL prefix support
- [ ] Signed URLs for private media
- [ ] Format negotiation (AVIF/WebP based on Accept header)
- [ ] Pre-generated responsive variants at upload

### Future (v2.2+)
- [ ] Lifecycle cleanup (auto-purge after 90 days)
- [ ] Video transcoding pipeline (HLS)
- [ ] Face detection for KYC selfies
- [ ] OCR for document scanning
- [ ] Bulk import/export for hosts

---

## 7. TROUBLESHOOTING

| Issue | Check | Fix |
|-------|-------|-----|
| Upload returns 400 "No file provided" | `request.files` empty | Ensure `enctype="multipart/form-data"` on form |
| Upload returns 400 "entity_id required" | Missing form field | Pass `entity_id` as form data |
| Processing stuck in "pending" | Celery worker not running | Start `celery -A app.celery_app worker` |
| File not found in production | `STORAGE_TYPE` mismatch | Ensure `STORAGE_TYPE=oci` with valid OCI creds |
| Duplicate upload not deduped | Hash mismatch | Check if file content actually changed |

---

## 8. REFERENCE: FAANG COMPARISON

| System | Approach | What AFCON360 Adopts |
|--------|----------|----------------------|
| **Amazon S3** | Content-addressable storage with SHA-256 dedup; lifecycle policies | ✅ SHA-256 dedup; ✅ Storage abstraction for local→OCI |
| **Facebook** | Unified media service; Haystack storage; CDN at edge; WebP/AVIF | ✅ Single API; ✅ WebP optimization; ✅ CDN-ready |
| **Google** | Async processing (Cloud Functions); Chrome formats; progressive loading | ✅ Celery workers; ✅ Responsive sizes; ✅ Low-bandwidth WebP |
| **TikTok** | No video storage — URLs only; H.265 encoding; thumbnails | ✅ YouTube URLs only; ✅ Image optimization; ✅ MIME validation |

---

*Last updated: 2026-06-29 | Maintained by Architecture Team*
```

### 10.2 Database Migration

```python
# migrations/versions/add_media_table.py

def upgrade():
    # Create unified media table
    op.create_table(
        'media',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('public_id', sa.String(64), nullable=False),
        sa.Column('module', sa.String(50), nullable=False),
        sa.Column('entity_id', sa.BigInteger(), nullable=False),
        sa.Column('storage_key', sa.String(500), nullable=False),
        sa.Column('urls', sa.JSON(), nullable=False),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('public_id'),
        sa.Index('idx_media_module_entity', 'module', 'entity_id'),
    )
```

### 10.3 Monitoring & Alerts

```python
# app/monitoring/media_metrics.py

class MediaMetrics:
    """Track media performance metrics"""
    
    @classmethod
    def track_upload(cls, file_size, duration, success):
        """Track upload performance"""
        # Send to Prometheus/Datadog
        
    @classmethod
    def track_optimization(cls, original_size, optimized_size):
        """Track optimization savings"""
        savings = (original_size - optimized_size) / original_size * 100
        
    @classmethod
    def track_bandwidth_savings(cls):
        """Calculate total bandwidth savings"""
        # Aggregate all optimizations
```

---

**Document Version**: 1.0  
**Last Updated**: 2026-06-27  
**Next Review**: 2026-07-04  
**Status**: Draft for Review