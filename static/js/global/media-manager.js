/**
 * AFCON360 Media Manager
 * Unified upload component for all modules
 */

class MediaManager {
    constructor(container, options = {}) {
        this.container = typeof container === 'string' ? document.querySelector(container) : container;
        if (!this.container) return;

        this.options = {
            module: this.container.dataset.module || 'accommodation',
            entityId: this.container.dataset.entityId || '',
            maxFiles: parseInt(this.container.dataset.maxFiles) || 20,
            maxSize: parseInt(this.container.dataset.maxSize) || 20 * 1024 * 1024,
            acceptedTypes: this.container.dataset.acceptedTypes?.split(',') || ['image/jpeg', 'image/png', 'image/webp', 'image/heic'],
            allowVideo: this.container.dataset.allowVideo === 'true',
            csrfToken: this.getCsrfToken(),
            ...options
        };

        this.uploadQueue = [];
        this.uploadedFiles = [];
        this.currentIndex = 0;
        this.isUploading = false;

        this.init();
    }

    /**
     * Get CSRF token from meta tag or form input
     */
    getCsrfToken() {
        // Try meta tag first (standard for AJAX)
        const metaToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
        if (metaToken) return metaToken;

        // Fallback to hidden input
        const inputToken = document.querySelector('input[name="csrf_token"]')?.value;
        if (inputToken) return inputToken;

        // Last resort: try to find any csrf token in the page
        const csrfInput = document.querySelector('[name="csrf_token"]');
        if (csrfInput) return csrfInput.value;

        console.warn('CSRF token not found');
        return '';
    }

    init() {
        this.initDropZone();
        this.initGallery();
        this.initKeyboardShortcuts();
        this.loadExistingMedia();
    }

    initDropZone() {
        const dropZone = this.container.querySelector('.drop-zone');
        const fileInput = this.container.querySelector('#fileInput');

        if (!dropZone || !fileInput) return;

        // Click to browse
        dropZone.addEventListener('click', (e) => {
            if (e.target.tagName !== 'BUTTON') {
                fileInput.click();
            }
        });

        // File input change
        fileInput.addEventListener('change', (e) => {
            this.handleFiles(e.target.files);
            fileInput.value = '';
        });

        // Drag and drop
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('drag-over');
        });

        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('drag-over');
        });

        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('drag-over');
            this.handleFiles(e.dataTransfer.files);
        });

        // Add drag and drop text update
        const dropText = dropZone.querySelector('.drop-zone-text');
        if (dropText) {
            dropText.innerHTML = `
                <span class="drop-icon">📁</span>
                <span class="drop-title">Drop files here or click to upload</span>
                <span class="drop-subtitle">Supported: ${this.options.acceptedTypes.join(', ')}</span>
            `;
        }
    }

    initGallery() {
        const gallery = this.container.querySelector('.media-grid');
        if (!gallery) return;

        // Delegate clicks for media actions
        gallery.addEventListener('click', (e) => {
            const btn = e.target.closest('[data-action]');
            if (!btn) return;

            const mediaId = btn.dataset.mediaId;
            const action = btn.dataset.action;

            switch (action) {
                case 'view':
                    this.openLightbox(parseInt(mediaId));
                    break;
                case 'set-cover':
                    this.setCover(parseInt(mediaId));
                    break;
                case 'delete':
                    this.deleteMedia(parseInt(mediaId));
                    break;
            }
        });
    }

    initKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            const lightbox = document.querySelector('.media-lightbox');
            if (!lightbox?.classList.contains('active')) return;

            if (e.key === 'Escape') this.closeLightbox();
            if (e.key === 'ArrowLeft') this.navigateLightbox(-1);
            if (e.key === 'ArrowRight') this.navigateLightbox(1);
        });
    }

    async loadExistingMedia() {
        const gallery = this.container.querySelector('.media-grid');
        if (!gallery || !this.options.entityId) return;

        try {
            // Show loading state
            gallery.innerHTML = `<div class="media-loading">Loading media...</div>`;

            const response = await fetch(
                `/api/media/entity/${this.options.module}/${this.options.entityId}`,
                { 
                    headers: { 
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                }
            );
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();

            if (data && Array.isArray(data)) {
                this.uploadedFiles = data;
                this.renderGallery();
            } else {
                this.uploadedFiles = [];
                this.renderGallery();
            }
        } catch (error) {
            console.error('Failed to load media:', error);
            const gallery = this.container.querySelector('.media-grid');
            if (gallery) {
                gallery.innerHTML = `<div class="media-error">Failed to load media. Please refresh.</div>`;
            }
        }
    }

    handleFiles(files) {
        const fileArray = Array.from(files);

        for (const file of fileArray) {
            // Check file count
            if (this.uploadedFiles.length + this.uploadQueue.length >= this.options.maxFiles) {
                alert(`Maximum ${this.options.maxFiles} files allowed`);
                break;
            }

            // Check file size
            if (file.size > this.options.maxSize) {
                alert(`File "${file.name}" exceeds maximum size of ${this.formatBytes(this.options.maxSize)}`);
                continue;
            }

            // Check file type
            if (!this.options.acceptedTypes.includes(file.type) && !this.options.allowVideo) {
                alert(`File type "${file.type}" not allowed. Supported: ${this.options.acceptedTypes.join(', ')}`);
                continue;
            }

            this.uploadQueue.push(file);
            this.renderUploadItem(file);
        }
    }

    async uploadFile(file) {
        if (!this.options.entityId) {
            console.error('Upload aborted: entity_id is missing from the media-uploader container.');
            const item = this.container.querySelector(`[data-file-name="${CSS.escape(file.name)}"]`);
            const statusEl = item?.querySelector('.upload-item-status');
            if (statusEl) {
                statusEl.textContent = '❌ No listing ID';
                statusEl.className = 'upload-item-status error';
                statusEl.title = 'Save the listing before uploading media.';
            }
            this.uploadQueue = this.uploadQueue.filter(f => f !== file);
            return;
        }

        const formData = new FormData();
        formData.append('file', file);
        formData.append('module', this.options.module);
        formData.append('entity_id', this.options.entityId);

        const item = this.container.querySelector(`[data-file-name="${CSS.escape(file.name)}"]`);
        const statusEl = item?.querySelector('.upload-item-status');
        const progressFill = this.container.querySelector('.upload-progress .progress-bar');
        const progressContainer = this.container.querySelector('.upload-progress');

        // Show progress container
        if (progressContainer) {
            progressContainer.style.display = 'block';
        }

        try {
            // ── Try pre-signed direct-to-storage upload first ──
            // The server returns a presigned URL only for backends that support
            // it (OCI/S3 in production). Local dev returns 501 → fall back.
            let usedPresigned = false;
            try {
                const presignResp = await fetch(`/api/media/presign/${this.options.module}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCsrfToken(),
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: JSON.stringify({
                        entity_id: this.options.entityId,
                        filename: file.name,
                        content_type: file.type || 'application/octet-stream',
                        total_size: file.size
                    })
                });

                if (presignResp.ok) {
                    const presign = await presignResp.json();
                    await this.uploadToPresignedUrl(file, presign, progressFill);
                    await fetch(presign.confirm_url, {
                        method: 'POST',
                        headers: {
                            'X-CSRFToken': this.getCsrfToken(),
                            'X-Requested-With': 'XMLHttpRequest'
                        }
                    });
                    usedPresigned = true;
                    // Build a minimal media record for immediate gallery render
                    this.uploadedFiles.push({
                        id: presign.media_id,
                        media_id: presign.media_id,
                        file_name: file.name,
                        media_type: file.type.startsWith('video/') ? 'video' : 'image',
                        is_cover: false,
                        status: 'processing'
                    });
                    this.uploadQueue = this.uploadQueue.filter(f => f !== file);
                    item?.remove();
                    if (progressContainer) { progressContainer.style.display = 'none'; }
                    if (progressFill) { progressFill.style.width = '0%'; progressFill.textContent = ''; }
                    this.renderGallery();
                    this.updateUploadCount();
                    this.loadExistingMedia(); // refresh once processing completes
                    return;
                }
            } catch (e) {
                console.warn('Presigned upload unavailable, falling back to streamed upload:', e);
            }

            if (!usedPresigned) {
                // ── Fallback: streamed upload through the app server ──
                const result = await this.streamUpload(file, formData, progressFill, progressContainer, item);
                if (result) {
                    const mediaData = {
                        id: result.media_id || result.id,
                        media_id: result.media_id || result.id,
                        url: result.url || result.urls?.original || '',
                        thumbnail_url: result.thumbnail_url || result.urls?.thumbnail || '',
                        file_name: result.file_name || file.name,
                        media_type: result.media_type || (file.type.startsWith('video/') ? 'video' : 'image'),
                        is_cover: result.is_cover || false,
                        ...result
                    };
                    this.uploadedFiles.push(mediaData);
                    this.uploadQueue = this.uploadQueue.filter(f => f !== file);
                    item?.remove();
                    if (progressContainer) { progressContainer.style.display = 'none'; }
                    if (progressFill) { progressFill.style.width = '0%'; progressFill.textContent = ''; }
                    this.renderGallery();
                    this.updateUploadCount();
                } else {
                    throw new Error('Upload failed - no response data');
                }
            }
        } catch (error) {
            console.error('Upload error:', error);
            if (statusEl) {
                statusEl.textContent = '❌ Failed';
                statusEl.className = 'upload-item-status error';
                statusEl.title = error.message;
            }
            
            // Hide progress on error
            if (progressContainer) {
                setTimeout(() => {
                    progressContainer.style.display = 'none';
                    if (progressFill) {
                        progressFill.style.width = '0%';
                        progressFill.textContent = '';
                    }
                }, 3000);
            }
        }
    }

    /**
     * Upload file bytes directly to the storage bucket using a pre-signed URL.
     * Bypasses the application server entirely (OCI/S3 production only).
     */
    uploadToPresignedUrl(file, presign, progressFill) {
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();

            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable && progressFill) {
                    const percent = Math.round((e.loaded / e.total) * 100);
                    progressFill.style.width = `${percent}%`;
                    progressFill.textContent = `${percent}%`;
                }
            });

            xhr.onload = () => {
                // S3/OCI presigned POST returns 204/200 on success.
                if (xhr.status >= 200 && xhr.status < 400) {
                    resolve();
                } else {
                    reject(new Error(`Direct upload failed (${xhr.status})`));
                }
            };
            xhr.onerror = () => reject(new Error('Network error during direct upload'));
            xhr.ontimeout = () => reject(new Error('Direct upload timed out'));
            xhr.timeout = 600000; // 10 min for large files

            if (presign.method === 'POST') {
                // Presigned POST: build multipart form with signed fields.
                const form = new FormData();
                for (const [k, v] of Object.entries(presign.fields || {})) {
                    form.append(k, v);
                }
                form.append('file', file);
                xhr.open('POST', presign.url);
                xhr.send(form);
            } else {
                // Presigned PUT: raw body with required headers.
                xhr.open('PUT', presign.url);
                for (const [k, v] of Object.entries(presign.headers || {})) {
                    xhr.setRequestHeader(k, v);
                }
                xhr.send(file);
            }
        });
    }

    /**
     * Fallback: stream the file through the Flask app server (local dev /
     * backends without pre-signed upload support).
     */
    streamUpload(file, formData, progressFill, progressContainer, item) {
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();

            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable && progressFill) {
                    const percent = Math.round((e.loaded / e.total) * 100);
                    progressFill.style.width = `${percent}%`;
                    progressFill.textContent = `${percent}%`;
                }
            });

            xhr.onload = () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    try {
                        resolve(JSON.parse(xhr.responseText));
                    } catch (e) {
                        reject(new Error('Invalid response from server'));
                    }
                } else {
                    let errorMsg = `Upload failed (${xhr.status})`;
                    try {
                        const errorData = JSON.parse(xhr.responseText);
                        errorMsg = errorData.error || errorMsg;
                    } catch (e) {
                        if (xhr.statusText) errorMsg = `${errorMsg}: ${xhr.statusText}`;
                    }
                    reject(new Error(errorMsg));
                }
            };
            xhr.onerror = () => reject(new Error('Network error - upload failed'));
            xhr.ontimeout = () => reject(new Error('Upload timeout - server took too long'));

            xhr.open('POST', `/api/media/upload/${this.options.module}`);
            xhr.setRequestHeader('Accept', 'application/json');
            xhr.timeout = 120000;

            const csrfToken = this.getCsrfToken();
            if (csrfToken) {
                xhr.setRequestHeader('X-CSRFToken', csrfToken);
            } else {
                console.warn('No CSRF token available for upload');
            }

            xhr.send(formData);
        });
    }

    renderUploadItem(file) {
        const queue = this.container.querySelector('.upload-queue');
        if (!queue) return;

        const item = document.createElement('div');
        item.className = 'upload-item';
        item.dataset.fileName = file.name;
        
        const previewUrl = URL.createObjectURL(file);
        const isVideo = file.type.startsWith('video/');
        
        item.innerHTML = `
            <div class="upload-item-preview">
                ${isVideo 
                    ? `<video src="${previewUrl}" muted preload="metadata"></video>`
                    : `<img src="${previewUrl}" alt="${file.name}" loading="lazy">`
                }
            </div>
            <div class="upload-item-info">
                <div class="upload-item-name" title="${file.name}">${file.name}</div>
                <div class="upload-item-size">${this.formatBytes(file.size)}</div>
                <div class="upload-item-type">${file.type || 'Unknown'}</div>
            </div>
            <span class="upload-item-status uploading">⏳ Uploading...</span>
            <button class="upload-item-remove" data-action="remove-upload" data-file="${file.name}" title="Cancel upload">&times;</button>
        `;

        queue.appendChild(item);

        // Remove button - cancel upload
        item.querySelector('.upload-item-remove').addEventListener('click', () => {
            this.uploadQueue = this.uploadQueue.filter(f => f !== file);
            item.remove();
            this.updateUploadCount();
        });

        // Start upload
        this.updateUploadCount();
        this.uploadFile(file);
    }

    renderGallery() {
        const gallery = this.container.querySelector('.media-grid');
        if (!gallery) return;

        if (this.uploadedFiles.length === 0) {
            gallery.innerHTML = `
                <div class="media-empty">
                    <span class="empty-icon">🖼️</span>
                    <p>No media uploaded yet</p>
                    <small>Upload images or videos using the drop zone above</small>
                </div>
            `;
            this.updateUploadCount();
            return;
        }

        // Sort: cover first, then by creation date
        const sortedFiles = [...this.uploadedFiles].sort((a, b) => {
            if (a.is_cover && !b.is_cover) return -1;
            if (!a.is_cover && b.is_cover) return 1;
            return 0;
        });

        gallery.innerHTML = sortedFiles.map((media, index) => {
            const actualIndex = this.uploadedFiles.indexOf(media);
            return `
                <div class="media-item" data-index="${actualIndex}" data-id="${media.id || media.media_id}">
                    ${this.renderMediaThumbnail(media)}
                    ${media.is_cover ? '<span class="media-cover-badge">⭐ Cover</span>' : ''}
                    <div class="media-item-overlay">
                        <div class="media-item-info">
                            <span class="media-item-name">${media.file_name || 'Untitled'}</span>
                        </div>
                        <div class="media-item-actions">
                            <button class="media-item-btn view" data-action="view" data-media-id="${media.id || media.media_id}" title="View">👁️</button>
                            ${!media.is_cover ? `<button class="media-item-btn cover" data-action="set-cover" data-media-id="${media.id || media.media_id}" title="Set as cover">⭐</button>` : ''}
                            <button class="media-item-btn delete" data-action="delete" data-media-id="${media.id || media.media_id}" title="Delete">🗑️</button>
                        </div>
                    </div>
                </div>
            `;
        }).join('');

        this.updateUploadCount();
    }

    renderMediaThumbnail(media) {
        const url = media.thumbnail_url || media.url || '';
        const fileName = media.file_name || 'Media';
        const type = media.media_type || 'image';

        if (type === 'video' || (media.url && media.url.match(/\.(mp4|webm|mov|avi)$/i))) {
            return `<video src="${media.url}" muted preload="metadata" poster="${media.thumbnail_url || ''}"></video>`;
        }
        
        if (url) {
            return `<img src="${url}" alt="${fileName}" loading="lazy" onerror="this.style.display='none'">`;
        }
        
        return `<div class="media-placeholder">📄</div>`;
    }

    updateUploadCount() {
        const countEl = this.container.querySelector('.media-count');
        if (countEl) {
            const total = this.uploadedFiles.length + this.uploadQueue.length;
            countEl.textContent = `${this.uploadedFiles.length} / ${this.options.maxFiles}`;
        }
    }

    async deleteMedia(mediaId) {
        if (!confirm('Are you sure you want to delete this media?')) return;

        const mediaItem = this.container.querySelector(`[data-id="${mediaId}"]`);
        if (mediaItem) {
            mediaItem.classList.add('deleting');
        }

        try {
            const response = await fetch(
                `/api/media/delete/${mediaId}`,
                {
                    method: 'DELETE',
                    headers: {
                        'X-CSRFToken': this.getCsrfToken(),
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                }
            );
            
            const data = await response.json();

            if (data.deleted || data.success) {
                this.uploadedFiles = this.uploadedFiles.filter(m => 
                    (m.id || m.media_id) !== parseInt(mediaId) && 
                    (m.id || m.media_id) !== mediaId
                );
                this.renderGallery();
                
                // Show success feedback
                this.showNotification('Media deleted successfully', 'success');
            } else {
                alert(data.error || 'Delete failed');
                if (mediaItem) {
                    mediaItem.classList.remove('deleting');
                }
            }
        } catch (error) {
            console.error('Delete error:', error);
            alert('Delete failed: ' + error.message);
            if (mediaItem) {
                mediaItem.classList.remove('deleting');
            }
        }
    }

    async setCover(mediaId) {
        // Check if set-cover endpoint exists
        try {
            const response = await fetch(
                `/api/media/set-cover/${mediaId}`,
                {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': this.getCsrfToken(),
                        'X-Requested-With': 'XMLHttpRequest',
                        'Content-Type': 'application/json'
                    }
                }
            );
            
            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    // Update local data
                    this.uploadedFiles = this.uploadedFiles.map(m => ({
                        ...m,
                        is_cover: (m.id || m.media_id) === parseInt(mediaId)
                    }));
                    this.renderGallery();
                    this.showNotification('Cover image updated', 'success');
                } else {
                    alert(data.error || 'Failed to set cover');
                }
            } else if (response.status === 404) {
                // Endpoint not implemented - just update locally
                this.uploadedFiles = this.uploadedFiles.map(m => ({
                    ...m,
                    is_cover: (m.id || m.media_id) === parseInt(mediaId)
                }));
                this.renderGallery();
                this.showNotification('Cover updated locally (server endpoint not available)', 'info');
            } else {
                const data = await response.json();
                alert(data.error || 'Failed to set cover');
            }
        } catch (error) {
            console.error('Set cover error:', error);
            // Fallback: update locally even if server fails
            this.uploadedFiles = this.uploadedFiles.map(m => ({
                ...m,
                is_cover: (m.id || m.media_id) === parseInt(mediaId)
            }));
            this.renderGallery();
            this.showNotification('Cover updated locally', 'info');
        }
    }

    openLightbox(index) {
        const lightbox = document.querySelector('.media-lightbox') || this.createLightbox();
        if (!lightbox) return;

        this.currentIndex = index;
        this.updateLightboxContent();
        lightbox.classList.add('active');
        document.body.style.overflow = 'hidden';
    }

    createLightbox() {
        const lightbox = document.createElement('div');
        lightbox.className = 'media-lightbox';
        lightbox.innerHTML = `
            <div class="media-lightbox-content">
                <button class="media-lightbox-close" data-action="close-lightbox">&times;</button>
                <div class="lightbox-media"></div>
                <button class="media-lightbox-nav media-lightbox-prev" data-action="prev">&#10094;</button>
                <button class="media-lightbox-nav media-lightbox-next" data-action="next">&#10095;</button>
                <div class="lightbox-info"></div>
            </div>
        `;
        document.body.appendChild(lightbox);

        // Bind events
        lightbox.querySelector('[data-action="close-lightbox"]')?.addEventListener('click', () => this.closeLightbox());
        lightbox.querySelector('[data-action="prev"]')?.addEventListener('click', () => this.navigateLightbox(-1));
        lightbox.querySelector('[data-action="next"]')?.addEventListener('click', () => this.navigateLightbox(1));
        
        // Close on backdrop click
        lightbox.addEventListener('click', (e) => {
            if (e.target === lightbox) this.closeLightbox();
        });

        return lightbox;
    }

    closeLightbox() {
        const lightbox = document.querySelector('.media-lightbox');
        if (lightbox) {
            lightbox.classList.remove('active');
            document.body.style.overflow = '';
        }
    }

    navigateLightbox(direction) {
        if (this.uploadedFiles.length === 0) return;
        
        this.currentIndex += direction;
        if (this.currentIndex < 0) this.currentIndex = this.uploadedFiles.length - 1;
        if (this.currentIndex >= this.uploadedFiles.length) this.currentIndex = 0;
        this.updateLightboxContent();
    }

    updateLightboxContent() {
        const media = this.uploadedFiles[this.currentIndex];
        if (!media) return;

        const content = document.querySelector('.media-lightbox-content');
        if (!content) return;

        const mediaContainer = content.querySelector('.lightbox-media');
        const infoContainer = content.querySelector('.lightbox-info');
        
        if (mediaContainer) {
            const type = media.media_type || 'image';
            const url = media.url || '';
            
            if (type === 'video' || (url && url.match(/\.(mp4|webm|mov|avi)$/i))) {
                mediaContainer.innerHTML = `<video src="${url}" controls autoplay></video>`;
            } else if (url) {
                mediaContainer.innerHTML = `<img src="${url}" alt="${media.file_name || 'Media'}" loading="lazy">`;
            } else {
                mediaContainer.innerHTML = `<div class="media-placeholder-large">🖼️</div>`;
            }
        }

        if (infoContainer) {
            const total = this.uploadedFiles.length;
            infoContainer.innerHTML = `
                <span class="lightbox-filename">${media.file_name || 'Untitled'}</span>
                <span class="lightbox-counter">${this.currentIndex + 1} of ${total}</span>
                ${media.is_cover ? '<span class="lightbox-cover-badge">⭐ Cover</span>' : ''}
            `;
        }

        // Update navigation buttons visibility
        const prevBtn = content.querySelector('[data-action="prev"]');
        const nextBtn = content.querySelector('[data-action="next"]');
        if (prevBtn) prevBtn.style.display = this.uploadedFiles.length > 1 ? '' : 'none';
        if (nextBtn) nextBtn.style.display = this.uploadedFiles.length > 1 ? '' : 'none';
    }

    showNotification(message, type = 'info') {
        // Simple notification system
        const existing = document.querySelector('.media-notification');
        if (existing) existing.remove();

        const notification = document.createElement('div');
        notification.className = `media-notification ${type}`;
        notification.textContent = message;
        document.body.appendChild(notification);

        // Auto-remove after 3 seconds
        setTimeout(() => {
            notification.classList.add('fade-out');
            setTimeout(() => notification.remove(), 300);
        }, 3000);
    }

    formatBytes(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    // Public API
    refresh() {
        this.loadExistingMedia();
    }

    getMedia() {
        return this.uploadedFiles;
    }

    getCover() {
        return this.uploadedFiles.find(m => m.is_cover) || this.uploadedFiles[0] || null;
    }

    clearQueue() {
        this.uploadQueue = [];
        const queue = this.container.querySelector('.upload-queue');
        if (queue) queue.innerHTML = '';
        this.updateUploadCount();
    }

    destroy() {
        // Clean up any event listeners or resources
        const lightbox = document.querySelector('.media-lightbox');
        if (lightbox) lightbox.remove();
        
        // Clear any object URLs
        this.container.querySelectorAll('img[src^="blob:"]').forEach(img => {
            URL.revokeObjectURL(img.src);
        });
    }
}

// Auto-initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.media-uploader').forEach(el => {
        // Check if already initialized
        if (!el._mediaManager) {
            el._mediaManager = new MediaManager(el);
        }
    });
});

// Also initialize for dynamically added elements
if (window.MutationObserver) {
    const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
            mutation.addedNodes.forEach((node) => {
                if (node.nodeType === 1) {
                    // Check if the node itself is a media-uploader
                    if (node.classList && node.classList.contains('media-uploader') && !node._mediaManager) {
                        node._mediaManager = new MediaManager(node);
                    }
                    // Check for media-uploader inside added node
                    node.querySelectorAll?.('.media-uploader:not([data-initialized])').forEach(el => {
                        if (!el._mediaManager) {
                            el._mediaManager = new MediaManager(el);
                            el.dataset.initialized = 'true';
                        }
                    });
                }
            });
        });
    });
    
    observer.observe(document.body, {
        childList: true,
        subtree: true
    });
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = MediaManager;
}