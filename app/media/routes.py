# app/media/routes.py

import uuid as uuid_lib
from flask import Blueprint, request, jsonify, current_app, send_from_directory, abort
from flask_login import login_required, current_user
from app.extensions import limiter, db

media_bp = Blueprint('media', __name__, url_prefix='/api/media')


def _can_manage_entity_media(module: str, entity_id: str, user) -> bool:
    """Authorize media writes against the owning entity, never a raw DB id."""
    if module != 'accommodation':
        return True

    from app.accommodation.models.property import Property
    from app.accommodation.services.identity_service import AccommodationIdentityService

    prop = db.session.query(Property).filter(
        Property.public_id == entity_id,
        Property.is_deleted == False,
    ).first()
    return bool(prop and AccommodationIdentityService.can_manage_property(
        user, prop.owner_user_id, prop.owner_org_id
    ))


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
    category = request.form.get('category', 'other')

    if not entity_id:
        return jsonify({'error': 'entity_id required'}), 400
    if not _can_manage_entity_media(module, entity_id, current_user):
        return jsonify({'error': 'You are not allowed to manage this property media'}), 403

    try:
        result = MediaService.upload_photo(
            file=file,
            module=module,
            entity_id=entity_id,
            uploader_user_id=current_user.id,  # internal BIGINT
            caption=caption,
            is_cover=is_cover,
            category=category,
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
    if not _can_manage_entity_media(module, data['entity_id'], current_user):
        return jsonify({'error': 'You are not allowed to manage this property media'}), 403

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
    media = db.session.query(Media).filter(
        Media.public_id == media_public_id,
        Media.is_deleted == False
    ).first()
    if not media:
        return jsonify({'error': 'Not found'}), 404
    if not _can_manage_entity_media(media.module, media.entity_id, current_user):
        return jsonify({'error': 'You are not allowed to view this media status'}), 403
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
        'category': (m.processing_metadata or {}).get('photo_category', 'other'),
        'is_cover': m.is_cover,
        'display_order': m.display_order,
        'status': m.status
    } for m in items])


@media_bp.route('/delete/<media_public_id>', methods=['DELETE'])
@login_required
def delete(media_public_id: str):
    """Soft-delete a media item."""
    from app.media.service import MediaService
    from app.media.models import Media

    media = db.session.query(Media).filter(
        Media.public_id == media_public_id,
        Media.is_deleted == False,
    ).first()
    if not media:
        return jsonify({'error': 'Not found or already deleted'}), 404
    if not _can_manage_entity_media(media.module, media.entity_id, current_user):
        return jsonify({'error': 'You are not allowed to manage this property media'}), 403
    success = MediaService.delete(media_public_id, current_user.id)
    if not success:
        return jsonify({'error': 'Not found or already deleted'}), 404
    return jsonify({'deleted': True})


@media_bp.route('/set-cover/<media_public_id>', methods=['POST'])
@login_required
def set_cover(media_public_id: str):
    """Set a media item as the cover image for its entity."""
    from app.media.models import Media

    media = db.session.query(Media).filter(
        Media.public_id == media_public_id,
        Media.is_deleted == False
    ).first()

    if not media:
        return jsonify({'error': 'Media not found'}), 404
    if not _can_manage_entity_media(media.module, media.entity_id, current_user):
        return jsonify({'error': 'You are not allowed to manage this property media'}), 403

    # Remove cover from other media for same entity
    db.session.query(Media).filter(
        Media.module == media.module,
        Media.entity_id == media.entity_id,
        Media.is_deleted == False
    ).update({'is_cover': False})

    # Set this as cover
    media.is_cover = True
    db.session.commit()

    return jsonify({'success': True, 'media_id': media_public_id})


@media_bp.route('/reorder/<module>/<entity_id>', methods=['POST'])
@login_required
def reorder(module: str, entity_id: str):
    """Persist a host's gallery order using public media identifiers."""
    from app.media.models import Media

    if not _can_manage_entity_media(module, entity_id, current_user):
        return jsonify({'error': 'You are not allowed to manage this property media'}), 403
    payload = request.get_json(silent=True) or {}
    media_ids = payload.get('media_ids')
    if not isinstance(media_ids, list) or len(media_ids) > 100:
        return jsonify({'error': 'media_ids must be a list of at most 100 items'}), 400

    items = db.session.query(Media).filter(
        Media.module == module,
        Media.entity_id == entity_id,
        Media.public_id.in_(media_ids),
        Media.is_deleted == False,
    ).all()
    if len(items) != len(media_ids):
        return jsonify({'error': 'One or more media items do not belong to this property'}), 400
    by_public_id = {item.public_id: item for item in items}
    for order, public_id in enumerate(media_ids):
        by_public_id[public_id].display_order = order
    db.session.commit()
    return jsonify({'success': True})


@media_bp.route('/health', methods=['GET'])
@login_required
def media_health():
    """
    Health check endpoint for media system.
    Returns system status, queue health, and processing metrics.
    """
    from sqlalchemy import func, literal, select
    from datetime import datetime, timezone

    try:
        db.session.execute(select(literal(1)))
        db_healthy = True
        db_error = None
    except Exception as e:
        db_healthy = False
        db_error = str(e)

    counts = {}
    for status_name in ['pending', 'processing', 'ready', 'failed']:
        counts[status_name] = db.session.scalar(
            select(func.count()).select_from(Media).where(Media.status == status_name)
        ) or 0

    counts['total'] = sum(counts.values())

    oldest_stuck = db.session.execute(
        select(
            Media.public_id,
            Media.status,
            Media.created_at,
            Media.processing_attempts,
        )
        .where(Media.status.in_(['pending', 'processing']))
        .order_by(Media.created_at.asc())
        .limit(1)
    ).first()

    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    failed_today = db.session.scalar(
        select(func.count())
        .select_from(Media)
        .where(Media.status == 'failed', Media.failed_at >= today)
    ) or 0

    celery_healthy = False
    celery_workers = 0
    try:
        from app.celery_app import celery_app
        inspect = celery_app.control.inspect()
        if inspect:
            active = inspect.active()
            if active:
                celery_healthy = True
                celery_workers = len(active)
    except Exception:
        celery_healthy = False

    if db_healthy and celery_healthy:
        overall_status = 'ok'
    elif db_healthy:
        overall_status = 'degraded'
    else:
        overall_status = 'unhealthy'

    return jsonify({
        'status': overall_status,
        'database': {
            'healthy': db_healthy,
            'error': db_error
        },
        'celery': {
            'healthy': celery_healthy,
            'workers': celery_workers
        },
        'media_counts': counts,
        'oldest_stuck': {
            'public_id': oldest_stuck[0] if oldest_stuck else None,
            'status': oldest_stuck[1] if oldest_stuck else None,
            'created_at': oldest_stuck[2].isoformat() if oldest_stuck else None,
            'attempts': oldest_stuck[3] if oldest_stuck else None
        } if oldest_stuck else None,
        'failed_today': failed_today,
        'timestamp': datetime.now(timezone.utc).isoformat()
    })


@media_bp.route('/admin/retry-failed', methods=['POST'])
@login_required
def retry_failed_media():
    """
    Admin endpoint to manually retry failed media.
    """
    from app.media.tasks import process_media_task
    from app.media.models import Media

    data = request.get_json() or {}
    media_id = data.get('media_id')

    if media_id:
        media = db.session.query(Media).filter(
            Media.public_id == media_id,
            Media.is_deleted == False
        ).first()
        if not media:
            return jsonify({'error': 'Media not found'}), 404

        media.status = 'pending'
        media.processing_attempts = 0
        media.failed_at = None
        db.session.commit()

        task = process_media_task.delay(media.id)
        return jsonify({
            'success': True,
            'media_id': media_id,
            'task_id': task.id,
            'message': 'Media re-queued for processing'
        })
    else:
        failed_media = db.session.query(Media).filter(
            Media.status == 'failed',
            Media.is_deleted == False
        ).all()
        count = len(failed_media)
        for media in failed_media:
            media.status = 'pending'
            media.processing_attempts = 0
            media.failed_at = None
            db.session.commit()
            process_media_task.delay(media.id)

        return jsonify({
            'success': True,
            'count': count,
            'message': f'Re-queued {count} failed media items for processing'
        })


@media_bp.route('/files/<path:filename>', methods=['GET'])
def serve_local_file(filename: str):
    """
    Serve local dev media files with correct MIME type detection and PDF inline support.
    In production (OCI), files are served directly from object storage.
    Only active when STORAGE_TYPE=local.
    """
    from flask import current_app
    if current_app.config.get('STORAGE_TYPE') != 'local':
        abort(404)
    base = current_app.config.get('MEDIA_LOCAL_PATH', '/tmp/afcon360_media')
    
    # Determine explicit mimetype for PDFs and common file types to prevent browser rendering issues
    mimetype = None
    if filename.lower().endswith('.pdf'):
        mimetype = 'application/pdf'
    elif filename.lower().endswith(('.jpg', '.jpeg')):
        mimetype = 'image/jpeg'
    elif filename.lower().endswith('.png'):
        mimetype = 'image/png'

    response = send_from_directory(base, filename, mimetype=mimetype)
    # Ensure inline viewing headers for documents and images
    if filename.lower().endswith(('.pdf', '.jpg', '.jpeg', '.png')):
        response.headers['Content-Disposition'] = 'inline'
    return response


# ============================================================================
# CHUNKED / RESUMABLE UPLOAD ENDPOINTS
# ============================================================================
# For large files on unreliable connections (African markets).
# Uses a simple chunked upload protocol with Redis for session state.

@media_bp.route('/upload/chunk/init', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def init_chunked_upload():
    """
    Initialize a chunked upload session.
    Returns upload_id for subsequent chunk uploads.
    """
    from app.media.service import MediaService
    from app.media.utils.quota_manager import QuotaManager

    data = request.get_json() or request.form
    module = data.get('module')
    entity_id = data.get('entity_id')
    filename = data.get('filename')
    total_size = int(data.get('total_size', 0))
    total_chunks = int(data.get('total_chunks', 0))

    if not all([module, entity_id, filename, total_size, total_chunks]):
        return jsonify({'error': 'Missing required fields'}), 400

    # Validate module
    module_config = current_app.config['MEDIA_MODULE_CONFIG'].get(module)
    if not module_config:
        return jsonify({'error': f"Unknown module: {module}"}), 400

    # Check file size
    max_size = module_config.get('max_size', 20 * 1024 * 1024)
    if total_size > max_size:
        return jsonify({'error': f"File too large. Max {max_size // (1024*1024)}MB"}), 400

    # Check quota
    try:
        QuotaManager.enforce_quota(current_user.id, total_size, module)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    # Create upload session
    upload_id = str(uuid_lib.uuid4())

    # Store session in Redis (or DB for persistence)
    from app.extensions import redis_client
    session_data = {
        'module': module,
        'entity_id': entity_id,
        'filename': filename,
        'total_size': total_size,
        'total_chunks': total_chunks,
        'uploaded_chunks': 0,
        'user_id': current_user.id,
        'content_type': data.get('content_type', 'application/octet-stream'),
    }
    redis_client.setex(
        f"upload_session:{upload_id}",
        3600,  # 1 hour expiry
        str(session_data)  # Simple serialization; use JSON in production
    )

    return jsonify({
        'upload_id': upload_id,
        'total_chunks': total_chunks,
        'chunk_size': total_size // total_chunks if total_chunks > 0 else 0
    }), 200


@media_bp.route('/upload/chunk/<upload_id>', methods=['PUT'])
@login_required
@limiter.limit("100 per minute")
def upload_chunk(upload_id: str):
    """
    Upload a single chunk of a file.
    """
    from app.extensions import redis_client

    if 'chunk' not in request.files:
        return jsonify({'error': 'No chunk provided'}), 400

    chunk = request.files['chunk']
    chunk_index = int(request.form.get('chunk_index', 0))

    # Get session
    session_key = f"upload_session:{upload_id}"
    session_data = redis_client.get(session_key)
    if not session_data:
        return jsonify({'error': 'Upload session expired or not found'}), 404

    # In production, use proper JSON serialization
    import ast
    session = ast.literal_eval(session_data.decode())

    # Verify user
    if session['user_id'] != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    # Store chunk (in production, use temporary file or S3 multipart)
    chunk_key = f"chunks/{upload_id}/{chunk_index}"
    backend = get_storage_backend()
    backend.save(chunk, chunk_key, chunk.content_type or 'application/octet-stream')

    # Update progress
    session['uploaded_chunks'] = session.get('uploaded_chunks', 0) + 1
    redis_client.setex(session_key, 3600, str(session))

    return jsonify({
        'chunk_index': chunk_index,
        'uploaded': session['uploaded_chunks'],
        'total': session['total_chunks']
    }), 200


@media_bp.route('/upload/chunk/<upload_id>/complete', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def complete_chunked_upload(upload_id: str):
    """
    Assemble chunks into final file and process.
    """
    from app.media.service import MediaService
    from app.media.storage import get_storage_backend
    from app.extensions import redis_client
    import io

    session_key = f"upload_session:{upload_id}"
    session_data = redis_client.get(session_key)
    if not session_data:
        return jsonify({'error': 'Upload session expired or not found'}), 404

    import ast
    session = ast.literal_eval(session_data.decode())

    if session['user_id'] != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    if session['uploaded_chunks'] != session['total_chunks']:
        return jsonify({'error': 'Not all chunks uploaded'}), 400

    # Assemble chunks
    backend = get_storage_backend()
    assembled = io.BytesIO()

    for i in range(session['total_chunks']):
        chunk_key = f"chunks/{upload_id}/{i}"
        chunk_data = backend.get_raw(chunk_key)
        if chunk_data:
            assembled.write(chunk_data.read())

    assembled.seek(0)

    # Create file-like object
    class ChunkedFile:
        def __init__(self, data, filename, content_type):
            self.data = data
            self.filename = filename
            self.content_type = content_type
            self.content_length = len(data.getvalue())

        def read(self, size=-1):
            return self.data.read(size)

        def seek(self, pos):
            return self.data.seek(pos)

        def tell(self):
            return self.data.tell()

    chunked_file = ChunkedFile(
        assembled,
        session['filename'],
        session.get('content_type', 'application/octet-stream')
    )

    try:
        result = MediaService.upload_photo(
            file=chunked_file,
            module=session['module'],
            entity_id=session['entity_id'],
            uploader_user_id=current_user.id,
            upload_session_id=upload_id
        )

        # Clean up chunks
        for i in range(session['total_chunks']):
            try:
                backend.delete(f"chunks/{upload_id}/{i}")
            except Exception:
                pass
        redis_client.delete(session_key)

        return jsonify(result), 202

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        current_app.logger.exception(f"Chunked upload complete error: {e}")
        return jsonify({'error': 'Upload failed'}), 500


@media_bp.route('/presign/<module>', methods=['POST'])
@login_required
@limiter.limit("30 per minute")
def presign(module: str):
    """
    Return a direct-to-storage (pre-signed) upload target so the client can
    PUT/POST the file bytes straight to the bucket, bypassing the app server.
    Only available for backends that support pre-signed uploads (OCI/S3).
    Local dev falls back to the streamed /upload endpoint (this returns 501).
    """
    from app.media.storage import get_storage_backend
    import uuid as _uuid

    data = request.get_json(silent=True) or request.form
    entity_id = data.get('entity_id')
    filename = data.get('filename')
    content_type = data.get('content_type', 'application/octet-stream')
    total_size = int(data.get('total_size', 0))
    category = data.get('category', 'other')

    if not all([entity_id, filename]):
        return jsonify({'error': 'entity_id and filename required'}), 400
    if not _can_manage_entity_media(module, entity_id, current_user):
        return jsonify({'error': 'You are not allowed to manage this property media'}), 403
    try:
        from app.media.service import MediaService
        category = MediaService.validate_photo_category(category)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    module_config = current_app.config['MEDIA_MODULE_CONFIG'].get(module)
    if not module_config:
        return jsonify({'error': f"Unknown module: {module}"}), 400

    max_size = module_config.get('max_size', 20 * 1024 * 1024)
    if total_size > max_size:
        return jsonify({'error': f"File too large. Max {max_size // (1024*1024)}MB"}), 400

    try:
        from app.media.utils.quota_manager import QuotaManager
        QuotaManager.enforce_quota(current_user.id, total_size, module)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception:
        pass

    backend = get_storage_backend()
    try:
        # SHA-256 unknown pre-upload; use a random key to avoid collisions.
        storage_key = f"{module}/{entity_id}/raw/{_uuid.uuid4().hex}_{filename}"
        target = backend.create_presigned_upload(
            storage_key, content_type, expires_in=900
        )
    except NotImplementedError:
        return jsonify({'error': 'pre-signed upload not supported for this storage backend'}), 501

    # Reserve a Media record in 'uploading' so processing can pick it up after
    # the client confirms the direct upload via /api/media/confirm.
    public_id = str(_uuid.uuid4())
    from app.media.models import Media
    media = Media(
        public_id=public_id,
        module=module,
        entity_id=entity_id,
        uploaded_by=current_user.id,
        media_type='photo',
        storage_key=storage_key,
        storage_backend=current_app.config.get('STORAGE_TYPE', 'local'),
        original_filename=filename,
        mime_type=content_type,
        file_size=total_size,
        processing_metadata={'photo_category': category},
        status='uploading',  # awaiting client confirmation of direct upload
    )
    db.session.add(media)
    db.session.commit()

    target['media_id'] = public_id
    target['storage_key'] = storage_key
    target['confirm_url'] = f"/api/media/confirm/{public_id}"
    return jsonify(target), 200


@media_bp.route('/confirm/<media_public_id>', methods=['POST'])
@login_required
@limiter.limit("30 per minute")
def confirm_upload(media_public_id: str):
    """
    Client calls this after a successful direct-to-storage upload to trigger
    async processing (resize/transcode) and final association.
    """
    from app.media.models import Media
    from app.media.tasks import process_media_task
    from app.media.storage import get_storage_backend

    media = db.session.query(Media).filter(
        Media.public_id == media_public_id,
        Media.is_deleted == False
    ).first()
    if not media:
        return jsonify({'error': 'Not found'}), 404
    if not _can_manage_entity_media(media.module, media.entity_id, current_user):
        return jsonify({'error': 'You are not allowed to manage this property media'}), 403

    # Validate the file actually landed in storage.
    backend = get_storage_backend()
    if not backend.exists(media.storage_key):
        return jsonify({'error': 'File not found in storage'}), 409

    media.status = 'pending'
    db.session.commit()
    task = process_media_task.delay(media.id)

    return jsonify({
        'media_id': media.public_id,
        'status': 'processing',
        'poll_url': f"/api/media/status/{media.public_id}",
        'celery_task_id': task.id,
    }), 202
@login_required
def get_quota():
    """Get current user's storage quota status."""
    from app.media.utils.quota_manager import QuotaManager

    module = request.args.get('module')
    status = QuotaManager.get_quota_status(current_user.id, module)
    return jsonify(status)
