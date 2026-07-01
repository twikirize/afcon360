# AFCON360 Media System — Setup & Usage Guide

**Audience:** Developers, DevOps, future maintainers  
**Last updated:** 2026-06-27  
**Status:** Production-ready

---

## 1. What This System Does

The unified media system replaces fragmented, URL-only media handling with a single service that:

- Accepts uploads from any module (accommodation, events, transport, KYC, etc.)
- Validates files (magic bytes, size, type)
- Stores files via pluggable backends (local disk or OCI Object Storage)
- Generates WebP thumbnails and responsive srcsets
- Tracks processing jobs via Celery
- Exposes a consistent REST API

---

## 2. Architecture Overview

```
Frontend (MediaManager JS)
    ↓
API: /api/media/upload/<module>
    ↓
MediaService.upload()
    ↓
StorageBackend.save()  ← LocalStorageBackend or OCIStorageBackend
    ↓
Celery: process_media_task()  → WebP generation, thumbnails
    ↓
Database: Media + MediaProcessingJob
```

---

## 3. Local Development Setup

### 3.1 Prerequisites

```bash
# Python deps (already in requirements.txt)
pip install -r requirements.txt
```

### 3.2 Environment Variables

Create or update `.env` in the project root:

```env
# Storage backend: 'local' or 'oci'
STORAGE_TYPE=local

# Local storage path (relative or absolute)
MEDIA_UPLOAD_PATH=./uploads

# Optional: CDN base URL (if using CloudFront/Cloudflare)
CDN_URL=
```

### 3.3 Run Migrations

```bash
flask db upgrade heads
```

> **Note:** The project has multiple Alembic heads. Always use `heads` (plural) or specify the target branch.

### 3.4 Start the App

```bash
# Terminal 1: Redis (required for Celery)
redis-server

# Terminal 2: Celery worker
celery -A app.celery_app worker --loglevel=info

# Terminal 3: Flask
flask run
```

### 3.5 Test the Upload Flow

1. Navigate to `/accommodation/host/create-listing`
2. Scroll to the **Media** section
3. Drag & drop images or click **Choose Files**
4. Verify uploads appear in the gallery grid

---

## 4. Oracle Cloud (OCI) Object Storage Setup

This is the recommended production backend for AFCON360.

### 4.1 Create OCI Resources

1. **Create a compartment** (or use the root compartment)
2. **Create a bucket:**
   - Name: `afcon360-media` (or your preferred name)
   - Storage tier: Standard
   - Visibility: Private
3. **Create an API key** for the instance/user that will upload:
   ```bash
   # Generate a new key pair (if needed)
   openssl genrsa -out oci_api_key.pem 2048
   openssl rsa -in oci_api_key.pem -pubout -out oci_api_key_public.pem
   ```
4. **Upload the public key** to OCI:
   - Console → Identity → Users → Your User → API Keys → Add Public Key
5. **Note the following values:**
   - Tenancy OCID
   - User OCID
   - Fingerprint of the public key
   - Region (e.g., `us-ashburn-1`, `af-johannesburg-1`)

### 4.2 Configure Environment Variables

```env
STORAGE_TYPE=oci

# OCI Object Storage
OCI_NAMESPACE=your_tenancy_namespace
OCI_BUCKET=afcon360-media
OCI_REGION=af-johannesburg-1
OCI_ACCESS_KEY=your_access_key_id
OCI_SECRET_KEY=your_private_key_pem_content
OCI_ENDPOINT=https://objectstorage.af-johannesburg-1.oraclecloud.com

# Optional: CDN (if using OCI CDN or CloudFront)
CDN_URL=https://cdn.yourdomain.com
```

> **Security note:** The `OCI_SECRET_KEY` is the full PEM content of your private key. Store it securely (e.g., in a secrets manager). Never commit it to Git.

### 4.3 IAM Policy (if using a separate user/group)

```json
{
  "policies": [
    {
      "name": "afcon360-media-upload",
      "statements": [
        {
          "effect": "allow",
          "actions": [
            "objectstorage:PutObject",
            "objectstorage:GetObject",
            "objectstorage:DeleteObject",
            "objectstorage:ListBucket"
          ],
          "resources": [
            "arn:aws:s3:::afcon360-media/*"
          ]
        }
      ]
    }
  ]
}
```

### 4.4 Verify Connectivity

```bash
python -c "
from app.media.storage import get_storage_backend
backend = get_storage_backend()
print(backend.__class__.__name__)  # Should print OCIStorageBackend
"
```

---

## 5. AWS S3 Setup (Alternative)

If you prefer AWS S3 over OCI:

```env
STORAGE_TYPE=s3
S3_BUCKET=afcon360-media
S3_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
```

---

## 6. Cloudinary Setup (Alternative)

For Cloudinary (managed image CDN):

```env
STORAGE_TYPE=cloudinary
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_key
CLOUDINARY_API_SECRET=your_secret
```

---

## 7. Module Configuration

Each module can have its own upload rules. Configure via `MEDIA_MODULE_CONFIG` in `app/config.py`:

```python
MEDIA_MODULE_CONFIG = {
    'accommodation': {
        'max_size': 20 * 1024 * 1024,  # 20MB
        'allowed_types': ['image/jpeg', 'image/png', 'image/webp', 'image/heic'],
        'path': 'properties'
    },
    'user': {
        'max_size': 5 * 1024 * 1024,   # 5MB
        'allowed_types': ['image/jpeg', 'image/png', 'image/webp'],
        'path': 'users'
    },
    'kyc': {
        'max_size': 10 * 1024 * 1024,  # 10MB
        'allowed_types': ['image/jpeg', 'image/png', 'image/webp', 'application/pdf'],
        'path': 'kyc'
    },
    'transport': {
        'max_size': 20 * 1024 * 1024,
        'allowed_types': ['image/jpeg', 'image/png', 'image/webp'],
        'path': 'transport'
    }
}
```

---

## 8. API Reference

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/media/upload/<module>` | Required | Upload a file |
| DELETE | `/api/media/delete/<module>/<media_id>` | Required | Delete media |
| POST | `/api/media/set-cover/<module>/<media_id>` | Required | Set as cover image |
| POST | `/api/media/optimize/<module>/<media_id>` | Required | Re-optimize media |
| GET | `/api/media/get/<module>/<entity_id>` | Required | List all media for entity |

### Upload Request

```bash
curl -X POST https://yourdomain.com/api/media/upload/accommodation \
  -F "file=@/path/to/image.jpg" \
  -F "module=accommodation" \
  -F "entity_id=123" \
  -H "Cookie: session=your_session_cookie"
```

### Upload Response

```json
{
  "success": true,
  "media": {
    "id": 42,
    "public_id": "550e8400-e29b-41d4-a716-446655440000",
    "file_name": "image.jpg",
    "file_size": 2048000,
    "mime_type": "image/jpeg",
    "media_type": "image",
    "url": "https://cdn.example.com/properties/42/original.jpg",
    "thumbnail_url": "https://cdn.example.com/properties/42/300w.jpg",
    "is_cover": false,
    "created_at": "2026-06-27T12:00:00Z"
  }
}
```

---

## 9. Frontend Usage

### 9.1 Basic Include

```html
{% include 'components/media_upload.html' %}
```

### 9.2 Custom Configuration

```html
<div class="media-uploader"
     data-module="events"
     data-entity-id="{{ event.id }}"
     data-max-files="10"
     data-max-size="10485760"
     data-accepted-types="image/jpeg,image/png,image/webp"
     data-allow-video="true">
</div>
```

### 9.3 CSS & JS

The uploader auto-initializes via `MediaManager` in `static/js/global/media-manager.js`.  
Styles are in `static/css/modules/media/media.css`.

---

## 10. Celery Tasks

The following tasks run asynchronously:

| Task | Description |
|------|-------------|
| `process_media_task` | Generate WebP, thumbnails, srcset |

### Monitoring

```bash
# Check active tasks
celery -A app.celery_app inspect active

# Check scheduled tasks
celery -A app.celery_app inspect scheduled
```

---

## 11. Troubleshooting

### "Multiple head revisions" error

```bash
flask db upgrade heads  # Use 'heads' (plural)
```

### Upload returns 413 (Payload Too Large)

Check `MEDIA_MODULE_CONFIG` for the module's `max_size`. Increase if needed.

### OCI upload fails with 403

- Verify `OCI_ACCESS_KEY` and `OCI_SECRET_KEY`
- Check IAM policy allows `objectstorage:PutObject`
- Ensure `OCI_ENDPOINT` matches your region

### Thumbnails not generating

- Verify Celery worker is running
- Check `app/media/processors/image.py` for errors
- Ensure `Pillow` is installed (`pip install pillow`)

---

## 12. Production Deployment Checklist

- [ ] Set `STORAGE_TYPE=oci` (or `s3`/`cloudinary`)
- [ ] Configure OCI/S3 credentials
- [ ] Set `CDN_URL` if using a CDN
- [ ] Run `flask db upgrade heads`
- [ ] Restart Gunicorn + Nginx
- [ ] Verify Celery worker is running
- [ ] Test upload via the UI
- [ ] Monitor OCI bucket for uploaded objects

---

## 13. Key Files Reference

| File | Purpose |
|------|---------|
| `app/media/models.py` | `Media`, `MediaProcessingJob` models |
| `app/media/service.py` | Core upload/delete/get logic |
| `app/media/routes.py` | Flask blueprint with all endpoints |
| `app/media/storage/oci.py` | OCI Object Storage backend |
| `app/media/processors/image.py` | WebP/thumbnail generation |
| `app/media/validators.py` | File validation (magic bytes, size) |
| `app/media/tasks.py` | Celery async tasks |
| `static/js/global/media-manager.js` | Frontend upload component |
| `templates/components/media_upload.html` | Reusable upload template |

---

## 14. Support

For issues or questions, refer to:
- `reports/media_system_implementation_report.md` — full implementation report
- `Readme's/media_handling.md` — original architecture document
- `prompts/MEDIA_SYSTEM_MASTER.md` — master specification
