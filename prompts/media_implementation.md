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