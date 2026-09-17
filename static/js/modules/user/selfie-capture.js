/**
 * AFCON360 Selfie Capture Module
 *
 * WebRTC-based front-camera selfie capture with:
 * - Live preview with positioning guide overlay
 * - Real-time quality feedback (brightness, framing)
 * - Capture → review → confirm/retake flow
 * - Base64 data-URL output for form submission
 * - Fallback to native file input when camera unavailable
 *
 * Usage:
 *   const capture = new SelfieCapture({ containerId: 'selfie-capture', onCapture: (dataUrl) => {} });
 *   capture.init();
 */
class SelfieCapture {
  constructor({ containerId, onCapture, onError }) {
    this.container = document.getElementById(containerId);
    this.onCapture = onCapture || function () {};
    this.onError = onError || function (err) { console.error('SelfieCapture:', err); };

    this.stream = null;
    this.videoEl = null;
    this.canvasEl = null;
    this.ctx = null;
    this.capturedDataUrl = null;
    this.isCapturing = false;
    this.facingMode = 'user';
    this.qualityCheckRAF = null;
  }

  async init() {
    if (!this.container) return;
    this._render();
    this.videoEl = this.container.querySelector('.sc-preview-video');
    this.canvasEl = this.container.querySelector('.sc-canvas');
    this.ctx = this.canvasEl.getContext('2d', { willReadFrequently: true });

    this.container.querySelector('.sc-btn-capture').addEventListener('click', () => this._capture());
    this.container.querySelector('.sc-btn-retake').addEventListener('click', () => this._retake());
    this.container.querySelector('.sc-btn-confirm').addEventListener('click', () => this._confirm());
    this.container.querySelector('.sc-btn-switch').addEventListener('click', () => this._switchCamera());

    const fallbackBtn = this.container.querySelector('.sc-fallback-btn');
    if (fallbackBtn) {
      fallbackBtn.addEventListener('click', () => this._showFallbackInput());
    }

    const fallbackInput = this.container.querySelector('.sc-fallback-input');
    if (fallbackInput) {
      fallbackInput.addEventListener('change', (e) => this._onFallbackFile(e));
    }

    await this._startCamera();
  }

  destroy() {
    this._stopCamera();
    if (this.qualityCheckRAF) cancelAnimationFrame(this.qualityCheckRAF);
  }

  /* ── Camera lifecycle ─────────────────────────────────── */

  async _startCamera() {
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: this.facingMode, width: { ideal: 1280 }, height: { ideal: 960 } },
        audio: false,
      });
      this.videoEl.srcObject = this.stream;
      this.videoEl.setAttribute('playsinline', 'true');
      await this.videoEl.play();
      this._setState('preview');
      this._startQualityCheck();
    } catch (err) {
      this._onCameraError(err);
    }
  }

  _stopCamera() {
    if (this.stream) {
      this.stream.getTracks().forEach(t => t.stop());
      this.stream = null;
    }
    if (this.videoEl) this.videoEl.srcObject = null;
  }

  async _switchCamera() {
    this.facingMode = this.facingMode === 'user' ? 'environment' : 'user';
    this._stopCamera();
    await this._startCamera();
  }

  _onCameraError(err) {
    const name = err.name || err.constructor.name;
    let msg = 'Camera access is required for selfie verification.';
    if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
      msg = 'Camera permission was denied. Please allow camera access in your browser settings and try again.';
    } else if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
      msg = 'No camera was found on this device. You can upload a selfie photo instead.';
    } else if (name === 'NotReadableError' || name === 'TrackStartError') {
      msg = 'Your camera is being used by another application. Please close other apps using the camera and try again.';
    }
    this._setState('unavailable', msg);
    this.onError(err);
  }

  /* ── Capture flow ─────────────────────────────────────── */

  _capture() {
    if (!this.stream || !this.videoEl.videoWidth) return;

    const vw = this.videoEl.videoWidth;
    const vh = this.videoEl.videoHeight;
    this.canvasEl.width = vw;
    this.canvasEl.height = vh;

    // Mirror for front camera
    if (this.facingMode === 'user') {
      this.ctx.translate(vw, 0);
      this.ctx.scale(-1, 1);
    }
    this.ctx.drawImage(this.videoEl, 0, 0, vw, vh);
    this.ctx.setTransform(1, 0, 0, 1, 0, 0);

    this.capturedDataUrl = this.canvasEl.toDataURL('image/jpeg', 0.92);
    this._stopCamera();
    if (this.qualityCheckRAF) cancelAnimationFrame(this.qualityCheckRAF);

    const quality = this._analyzeQuality();
    this._showReview(quality);
    this._setState('review');
  }

  _retake() {
    this.capturedDataUrl = null;
    this._setState('preview');
    this._startCamera();
  }

  _confirm() {
    if (!this.capturedDataUrl) return;
    this._setState('confirmed');
    this.onCapture(this.capturedDataUrl);
  }

  /* ── Quality analysis ─────────────────────────────────── */

  _startQualityCheck() {
    const check = () => {
      if (!this.stream || this.videoEl.paused) return;
      const q = this._analyzeLiveFrame();
      this._updateQualityIndicator(q);
      this.qualityCheckRAF = requestAnimationFrame(check);
    };
    this.qualityCheckRAF = requestAnimationFrame(check);
  }

  _analyzeLiveFrame() {
    if (!this.videoEl.videoWidth) return { brightness: 128, ok: false };

    const sampleW = 160;
    const sampleH = 120;
    const tmpCanvas = document.createElement('canvas');
    tmpCanvas.width = sampleW;
    tmpCanvas.height = sampleH;
    const tmpCtx = tmpCanvas.getContext('2d', { willReadFrequently: true });
    tmpCtx.drawImage(this.videoEl, 0, 0, sampleW, sampleH);
    const data = tmpCtx.getImageData(0, 0, sampleW, sampleH).data;

    let totalBrightness = 0;
    for (let i = 0; i < data.length; i += 16) {
      totalBrightness += (data[i] * 0.299 + data[i + 1] * 0.587 + data[i + 2] * 0.114);
    }
    const avgBrightness = totalBrightness / (data.length / 16);

    const brightOk = avgBrightness > 50 && avgBrightness < 220;
    return { brightness: avgBrightness, ok: brightOk };
  }

  _analyzeQuality() {
    if (!this.capturedDataUrl) return { score: 0, issues: ['No image captured'] };

    const img = new Image();
    img.src = this.capturedDataUrl;

    const issues = [];
    let score = 100;

    // Brightness check from canvas
    const w = this.canvasEl.width;
    const h = this.canvasEl.height;
    const sampleW = Math.min(320, w);
    const sampleH = Math.min(240, h);
    const tmpCanvas = document.createElement('canvas');
    tmpCanvas.width = sampleW;
    tmpCanvas.height = sampleH;
    const tmpCtx = tmpCanvas.getContext('2d', { willReadFrequently: true });
    tmpCtx.drawImage(this.canvasEl, 0, 0, w, h, 0, 0, sampleW, sampleH);
    const data = tmpCtx.getImageData(0, 0, sampleW, sampleH).data;

    let totalBrightness = 0;
    let darkPixels = 0;
    let brightPixels = 0;
    const pixelCount = data.length / 4;

    for (let i = 0; i < data.length; i += 4) {
      const lum = data[i] * 0.299 + data[i + 1] * 0.587 + data[i + 2] * 0.114;
      totalBrightness += lum;
      if (lum < 30) darkPixels++;
      if (lum > 240) brightPixels++;
    }
    const avgBrightness = totalBrightness / pixelCount;
    const darkRatio = darkPixels / pixelCount;
    const brightRatio = brightPixels / pixelCount;

    if (avgBrightness < 50) { issues.push('Image is too dark'); score -= 30; }
    else if (avgBrightness < 70) { issues.push('Image may be too dark'); score -= 10; }
    if (avgBrightness > 220) { issues.push('Image is overexposed'); score -= 30; }
    else if (avgBrightness > 190) { issues.push('Image may be overexposed'); score -= 10; }
    if (darkRatio > 0.6) { issues.push('Most of the image is dark'); score -= 20; }
    if (brightRatio > 0.5) { issues.push('Most of the image is bright/white'); score -= 20; }

    // Resolution check
    if (w < 400 || h < 300) { issues.push('Image resolution is too low'); score -= 25; }

    // Color variance check (low variance = likely blank/uniform)
    let rSum = 0, gSum = 0, bSum = 0;
    for (let i = 0; i < data.length; i += 16) {
      rSum += data[i]; gSum += data[i + 1]; bSum += data[i + 2];
    }
    const samples = data.length / 16;
    const rAvg = rSum / samples, gAvg = gSum / samples, bAvg = bSum / samples;
    let rVar = 0, gVar = 0, bVar = 0;
    for (let i = 0; i < data.length; i += 16) {
      rVar += (data[i] - rAvg) ** 2;
      gVar += (data[i + 1] - gAvg) ** 2;
      bVar += (data[i + 2] - bAvg) ** 2;
    }
    const variance = (rVar + gVar + bVar) / (samples * 3);
    if (variance < 50) { issues.push('Image appears uniform — make sure your face is visible'); score -= 25; }

    return { score: Math.max(0, score), issues, brightness: avgBrightness, variance };
  }

  /* ── UI rendering ─────────────────────────────────────── */

  _render() {
    this.container.innerHTML = `
      <div class="sc-wrapper" data-state="preview">
        <div class="sc-camera-section">
          <div class="sc-preview-container">
            <video class="sc-preview-video" autoplay playsinline muted></video>
            <canvas class="sc-canvas" style="display:none;"></canvas>
            <img class="sc-review-img" style="display:none;" alt="Captured selfie">

            <div class="sc-guide-overlay">
              <div class="sc-guide-oval"></div>
              <div class="sc-guide-labels">
                <span class="sc-label sc-label-face">Face</span>
                <span class="sc-label sc-label-shoulders">Shoulders</span>
                <span class="sc-label sc-label-chest">Chest</span>
              </div>
              <div class="sc-guide-corners">
                <span class="sc-corner sc-corner-tl"></span>
                <span class="sc-corner sc-corner-tr"></span>
                <span class="sc-corner sc-corner-bl"></span>
                <span class="sc-corner sc-corner-br"></span>
              </div>
            </div>

            <div class="sc-quality-badge" style="display:none;">
              <span class="sc-quality-dot"></span>
              <span class="sc-quality-text">Checking...</span>
            </div>
          </div>

          <div class="sc-preview-actions">
            <button type="button" class="sc-btn sc-btn-switch" title="Switch camera">
              <i class="bi bi-camera-reverse"></i>
            </button>
            <button type="button" class="sc-btn sc-btn-capture" title="Take selfie">
              <span class="sc-btn-capture-ring"></span>
            </button>
            <button type="button" class="sc-btn sc-btn-retake" title="Retake" style="display:none;">
              <i class="bi bi-arrow-counterclockwise"></i>
            </button>
          </div>
        </div>

        <div class="sc-review-section" style="display:none;">
          <div class="sc-review-container">
            <img class="sc-review-confirm-img" alt="Your selfie">
            <div class="sc-review-quality" style="display:none;">
              <i class="bi bi-info-circle"></i>
              <span class="sc-review-quality-text"></span>
            </div>
          </div>
          <div class="sc-review-actions">
            <button type="button" class="sc-btn-secondary sc-btn-retake-review">
              <i class="bi bi-arrow-counterclockwise"></i> Retake
            </button>
            <button type="button" class="sc-btn-primary sc-btn-confirm">
              <i class="bi bi-check-lg"></i> Use This Selfie
            </button>
          </div>
        </div>

        <div class="sc-confirmed-section" style="display:none;">
          <div class="sc-confirmed-badge">
            <i class="bi bi-check-circle-fill"></i>
            <span>Selfie captured</span>
          </div>
          <button type="button" class="sc-btn-link sc-btn-retake-confirmed">Retake selfie</button>
        </div>

        <div class="sc-unavailable-section" style="display:none;">
          <div class="sc-unavailable-icon"><i class="bi bi-camera-video-off"></i></div>
          <p class="sc-unavailable-msg"></p>
          <button type="button" class="sc-btn-secondary sc-fallback-btn">
            <i class="bi bi-upload"></i> Upload a selfie photo instead
          </button>
          <input type="file" class="sc-fallback-input" accept="image/*" capture="user" style="display:none;">
        </div>
      </div>
    `;
  }

  _setState(state, msg) {
    const wrapper = this.container.querySelector('.sc-wrapper');
    wrapper.setAttribute('data-state', state);

    const sections = {
      preview: '.sc-camera-section',
      review: '.sc-review-section',
      confirmed: '.sc-confirmed-section',
      unavailable: '.sc-unavailable-section',
    };
    Object.entries(sections).forEach(([key, sel]) => {
      const el = this.container.querySelector(sel);
      if (el) el.style.display = key === state ? '' : 'none';
    });

    const video = this.container.querySelector('.sc-preview-video');
    const reviewImg = this.container.querySelector('.sc-review-img');
    const captureBtn = this.container.querySelector('.sc-btn-capture');
    const retakeBtn = this.container.querySelector('.sc-btn-retake');
    const switchBtn = this.container.querySelector('.sc-btn-switch');

    if (state === 'preview') {
      if (video) video.style.display = '';
      if (reviewImg) reviewImg.style.display = 'none';
      if (captureBtn) captureBtn.style.display = '';
      if (retakeBtn) retakeBtn.style.display = 'none';
      if (switchBtn) switchBtn.style.display = '';
    }

    if (state === 'unavailable' && msg) {
      const msgEl = this.container.querySelector('.sc-unavailable-msg');
      if (msgEl) msgEl.textContent = msg;
    }
  }

  _showReview(quality) {
    const reviewImg = this.container.querySelector('.sc-review-confirm-img');
    if (reviewImg) reviewImg.src = this.capturedDataUrl;

    const reviewVideo = this.container.querySelector('.sc-review-img');
    if (reviewVideo) {
      reviewVideo.src = this.capturedDataUrl;
      reviewVideo.style.display = '';
    }

    const video = this.container.querySelector('.sc-preview-video');
    if (video) video.style.display = 'none';

    const qualityEl = this.container.querySelector('.sc-review-quality');
    const qualityText = this.container.querySelector('.sc-review-quality-text');
    if (qualityEl && qualityText && quality.issues && quality.issues.length > 0) {
      qualityEl.style.display = '';
      qualityText.textContent = quality.issues.join('. ') + '. You can still submit, but a clear photo speeds up verification.';
    } else if (qualityEl) {
      qualityEl.style.display = 'none';
    }
  }

  _updateQualityIndicator(q) {
    const badge = this.container.querySelector('.sc-quality-badge');
    const dot = this.container.querySelector('.sc-quality-dot');
    const text = this.container.querySelector('.sc-quality-text');
    if (!badge || !dot || !text) return;

    badge.style.display = '';
    if (q.ok) {
      dot.className = 'sc-quality-dot sc-quality-ok';
      text.textContent = 'Good lighting';
    } else {
      dot.className = 'sc-quality-dot sc-quality-warn';
      if (q.brightness < 50) text.textContent = 'Too dark — find better light';
      else if (q.brightness > 220) text.textContent = 'Too bright — reduce light';
      else text.textContent = 'Adjust lighting';
    }
  }

  /* ── Fallback (file input) ────────────────────────────── */

  _showFallbackInput() {
    const input = this.container.querySelector('.sc-fallback-input');
    if (input) input.click();
  }

  _onFallbackFile(e) {
    const file = e.target.files[0];
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      this.onError(new Error('Please select an image file'));
      return;
    }
    const reader = new FileReader();
    reader.onload = (ev) => {
      this.capturedDataUrl = ev.target.result;
      this._setState('confirmed');
      this.onCapture(this.capturedDataUrl);
    };
    reader.readAsDataURL(file);
  }
}
