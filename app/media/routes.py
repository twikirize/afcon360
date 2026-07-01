# app/media/routes.py

import uuid
from flask import Blueprint, request, jsonify, current_app, send_from_directory, abort
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
    media = db.session.query(Media).filter(
        Media.public_id == media_public_id,
        Media.is_deleted == False
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
    from flask import current_app
    if current_app.config.get('STORAGE_TYPE') != 'local':
        abort(404)
    base = current_app.config.get('MEDIA_LOCAL_PATH', '/tmp/afcon360_media')
    return send_from_directory(base, filename)


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


@media_bp.route('/quota', methods=['GET'])
@login_required
def get_quota():
    """Get current user's storage quota status."""
    from app.media.utils.quota_manager import QuotaManager

    module = request.args.get('module')
    status = QuotaManager.get_quota_status(current_user.id, module)
    return jsonify(status)
