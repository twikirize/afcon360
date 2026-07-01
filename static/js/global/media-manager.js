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
            csrfToken: document.querySelector('meta[name="csrf-token"]')?.content || '',
            ...options
        };

        this.uploadQueue = [];
        this.uploadedFiles = [];
        this.currentIndex = 0;

        this.init();
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
            const response = await fetch(
                `/api/media/get/${this.options.module}/${this.options.entityId}`,
                { headers: { 'X-Requested-With': 'XMLHttpRequest' } }
            );
            const data = await response.json();

            if (data.success) {
                this.uploadedFiles = data.media || [];
                this.renderGallery();
            }
        } catch (error) {
            console.error('Failed to load media:', error);
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
                alert(`File type "${file.type}" not allowed`);
                continue;
            }

            this.uploadQueue.push(file);
            this.renderUploadItem(file);
        }
    }

    async uploadFile(file) {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('module', this.options.module);
        formData.append('entity_id', this.options.entityId);
        formData.append('csrf_token', this.options.csrfToken);

        const item = this.container.querySelector(`[data-file-name="${file.name}"]`);
        const statusEl = item?.querySelector('.upload-item-status');
        const progressBar = this.container.querySelector('.upload-progress .progress-bar');

        try {
            const xhr = new XMLHttpRequest();

            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable && progressBar) {
                    const percent = (e.loaded / e.total) * 100;
                    progressBar.style.width = `${percent}%`;
                }
            });

            const uploadPromise = new Promise((resolve, reject) => {
                xhr.onload = () => {
                    if (xhr.status === 200) {
                        resolve(JSON.parse(xhr.responseText));
                    } else {
                        reject(new Error(xhr.responseText));
                    }
                };
                xhr.onerror = () => reject(new Error('Upload failed'));
            });

            xhr.open('POST', '/api/media/upload');
            xhr.send(formData);
            const result = await uploadPromise;

            if (result.success) {
                this.uploadedFiles.push(result.media);
                this.uploadQueue = this.uploadQueue.filter(f => f !== file);
                item?.remove();
                this.renderGallery();
            } else {
                throw new Error(result.error || 'Upload failed');
            }
        } catch (error) {
            console.error('Upload error:', error);
            if (statusEl) {
                statusEl.textContent = 'Failed';
                statusEl.className = 'upload-item-status error';
            }
        }
    }

    renderUploadItem(file) {
        const queue = this.container.querySelector('.upload-queue');
        if (!queue) return;

        const item = document.createElement('div');
        item.className = 'upload-item';
        item.dataset.fileName = file.name;
        item.innerHTML = `
            <img class="upload-item-thumb" src="${URL.createObjectURL(file)}" alt="">
            <div class="upload-item-info">
                <div class="upload-item-name">${file.name}</div>
                <div class="upload-item-size">${this.formatBytes(file.size)}</div>
            </div>
            <span class="upload-item-status uploading">Uploading...</span>
            <button class="upload-item-remove" data-action="remove-upload" data-file="${file.name}">&times;</button>
        `;

        queue.appendChild(item);

        // Remove button
        item.querySelector('.upload-item-remove').addEventListener('click', () => {
            this.uploadQueue = this.uploadQueue.filter(f => f !== file);
            item.remove();
        });

        // Start upload
        this.uploadFile(file);
    }

    renderGallery() {
        const gallery = this.container.querySelector('.media-grid');
        if (!gallery) return;

        gallery.innerHTML = this.uploadedFiles.map((media, index) => `
            <div class="media-item" data-index="${index}">
                ${this.renderMediaThumbnail(media)}
                ${media.is_cover ? '<span class="media-cover-badge">Cover</span>' : ''}
                <div class="media-item-overlay">
                    <div class="media-item-actions">
                        <button class="media-item-btn primary" data-action="view" data-media-id="${media.id}">View</button>
                        ${!media.is_cover ? `<button class="media-item-btn primary" data-action="set-cover" data-media-id="${media.id}">Cover</button>` : ''}
                        <button class="media-item-btn danger" data-action="delete" data-media-id="${media.id}">Delete</button>
                    </div>
                </div>
            </div>
        `).join('');
    }

    renderMediaThumbnail(media) {
        if (media.media_type === 'video') {
            return `<video src="${media.url}" muted preload="metadata"></video>`;
        }
        return `<img src="${media.thumbnail_url || media.url}" alt="${media.file_name}" loading="lazy">`;
    }

    async deleteMedia(mediaId) {
        if (!confirm('Are you sure you want to delete this media?')) return;

        try {
            const response = await fetch(
                `/api/media/delete/${this.options.module}/${mediaId}`,
                {
                    method: 'DELETE',
                    headers: {
                        'X-CSRFToken': this.options.csrfToken,
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                }
            );
            const data = await response.json();

            if (data.success) {
                this.uploadedFiles = this.uploadedFiles.filter(m => m.id !== mediaId);
                this.renderGallery();
            } else {
                alert(data.error || 'Delete failed');
            }
        } catch (error) {
            console.error('Delete error:', error);
            alert('Delete failed');
        }
    }

    async setCover(mediaId) {
        try {
            const response = await fetch(
                `/api/media/set-cover/${this.options.module}/${mediaId}`,
                {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': this.options.csrfToken,
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                }
            );
            const data = await response.json();

            if (data.success) {
                this.uploadedFiles = this.uploadedFiles.map(m => ({
                    ...m,
                    is_cover: m.id === mediaId
                }));
                this.renderGallery();
            }
        } catch (error) {
            console.error('Set cover error:', error);
        }
    }

    openLightbox(index) {
        const lightbox = document.querySelector('.media-lightbox');
        if (!lightbox) return;

        this.currentIndex = index;
        this.updateLightboxContent();
        lightbox.classList.add('active');
    }

    closeLightbox() {
        const lightbox = document.querySelector('.media-lightbox');
        if (lightbox) lightbox.classList.remove('active');
    }

    navigateLightbox(direction) {
        this.currentIndex += direction;
        if (this.currentIndex < 0) this.currentIndex = this.uploadedFiles.length - 1;
        if (this.currentIndex >= this.uploadedFiles.length) this.currentIndex = 0;
        this.updateLightboxContent();
    }

    updateLightboxContent() {
        const content = document.querySelector('.media-lightbox-content');
        if (!content) return;

        const media = this.uploadedFiles[this.currentIndex];
        if (!media) return;

        content.innerHTML = `
            <button class="media-lightbox-close" data-action="close-lightbox">&times;</button>
            ${media.media_type === 'video'
                ? `<video src="${media.url}" controls autoplay></video>`
                : `<img src="${media.url}" alt="${media.file_name}">`
            }
            <button class="media-lightbox-nav media-lightbox-prev" data-action="prev">&#10094;</button>
            <button class="media-lightbox-nav media-lightbox-next" data-action="next">&#10095;</button>
        `;

        // Re-bind lightbox events
        content.querySelector('[data-action="close-lightbox"]')?.addEventListener('click', () => this.closeLightbox());
        content.querySelector('[data-action="prev"]')?.addEventListener('click', () => this.navigateLightbox(-1));
        content.querySelector('[data-action="next"]')?.addEventListener('click', () => this.navigateLightbox(1));
    }

    formatBytes(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
}

// Auto-initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.media-uploader').forEach(el => {
        new MediaManager(el);
    });
});
