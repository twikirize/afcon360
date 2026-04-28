/* Admin moderation JS — externalized to work under strict CSP without inline handlers */
(function(){
  'use strict';

  // State for modals
  let _modalSlug = null;
  let _modalName = '';

  // Utility: parse arguments from an inline onclick string like quickAction('approve','slug','Name')
  function parseArgsFromOnclick(attr) {
    if (!attr) return [];
    const m = attr.match(/\((.*)\)/);
    if (!m) return [];
    const inside = m[1];
    // Split by comma but respect quotes; also decode HTML entities for common cases
    const args = [];
    let cur = '';
    let quote = null;
    for (let i = 0; i < inside.length; i++) {
      const ch = inside[i];
      if ((ch === '"' || ch === "'") && !quote) {
        quote = ch;
        continue;
      } else if (quote && ch === quote) {
        quote = null;
        continue;
      }
      if (ch === ',' && !quote) {
        args.push(cur.trim());
        cur = '';
      } else {
        cur += ch;
      }
    }
    if (cur.length) args.push(cur.trim());
    return args.map(a => a.replace(/^['"]|['"]$/g, ''));
  }

  function showToast(message, type = 'success') {
    let stack = document.getElementById('toastStack');
    if (!stack) {
      stack = document.createElement('div');
      stack.id = 'toastStack';
      stack.className = 'toast-stack';
      document.body.appendChild(stack);
    }
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<i class="fas fa-${type === 'success' ? 'check-circle' : 'exclamation-circle'}"></i> ${message}`;
    stack.appendChild(toast);
    setTimeout(() => { toast.classList.add('toast-out'); setTimeout(() => toast.remove(), 350); }, 4000);
  }

  function shakeField(id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.style.animation = 'none';
    el.style.borderColor = '#ff3c3c';
    // reflow
    void el.offsetHeight;
    el.style.animation = 'shake .4s ease';
    el.focus();
  }

  function openModal(action, slug, name) {
    _modalSlug = slug || null;
    _modalName = name || '';
    const sub = document.getElementById(`mod-${action}-sub`);
    if (sub && name) {
      const base = sub.dataset.base || sub.textContent;
      sub.dataset.base = base;
      sub.innerHTML = `<strong style="color:var(--brand-text)">"${name}"</strong> — ${base}`;
    }
    const overlay = document.getElementById(`mod-${action}`);
    if (overlay) {
      // persist slug on the modal element as a secondary source of truth
      overlay.dataset.slug = slug || '';
      overlay.classList.add('open');
    }
    document.querySelectorAll(`#mod-${action} textarea`).forEach(t => t.value = '');
    document.querySelectorAll(`#mod-${action} select`).forEach(s => { if (s.id !== 'suspend-duration') s.value = ''; });
  }

  function closeModal(action) {
    const overlay = document.getElementById(`mod-${action}`);
    if (overlay) overlay.classList.remove('open');
    _modalSlug = null;
  }

  function submitModal(action) {
    // Derive slug from state or modal dataset as a fallback
    let slug = _modalSlug;
    if (!slug) {
      const overlay = document.getElementById(`mod-${action}`);
      if (overlay && overlay.dataset && overlay.dataset.slug) {
        slug = overlay.dataset.slug;
      }
    }

    let payload = {};
    if (action === 'reject') {
      const reason = (document.getElementById('reject-reason') || {}).value || '';
      const r = reason.trim();
      if (!r) { shakeField('reject-reason'); return; }
      payload = { reason: r };
    } else if (action === 'suspend') {
      const reason = (document.getElementById('suspend-reason') || {}).value || '';
      const r = reason.trim();
      if (!r) { shakeField('suspend-reason'); return; }
      const duration = (document.getElementById('suspend-duration') || {}).value || '7d';
      payload = { reason: r, duration };
    } else if (action === 'takedown') {
      const category = (document.getElementById('takedown-category') || {}).value || '';
      const reason = ((document.getElementById('takedown-reason') || {}).value || '').trim();
      const notify = (document.getElementById('takedown-notify') || {}).checked || false;
      if (!category) { shakeField('takedown-category'); return; }
      if (!reason)   { shakeField('takedown-reason');   return; }
      payload = { category, reason, notify_organiser: notify };
    } else if (action === 'deactivate') {
      const reason = ((document.getElementById('deactivate-reason') || {}).value || '').trim();
      if (!reason) { shakeField('deactivate-reason'); return; }
      payload = { reason };
    }

    if (!slug) {
      showToast('Missing event identifier. Please close and reopen the modal, then try again.', 'error');
      return;
    }

    closeModal(action);
    callModerationAPI(action, slug, payload);
  }

  // Attempt to derive a stable identifier from DOM context when slug is missing
  function resolveIdentifierFromDOM(el) {
    if (!el || !el.closest) return '';
    // 1) row-<identifier>
    const row = el.closest('[id^="row-"]');
    if (row && row.id) {
      const sid = row.id.replace(/^row-/, '').trim();
      if (sid) return sid;
    }
    // 2) data attributes
    const withData = el.closest('[data-slug],[data-identifier]');
    if (withData) {
      const val = (withData.getAttribute('data-slug') || withData.getAttribute('data-identifier') || '').trim();
      if (val) return val;
    }
    // 3) links that contain the slug, prefer admin endpoints or public event page
    const link = (el.closest('tr') || document).querySelector('a[href*="/events/"]');
    if (link) {
      try {
        const href = link.getAttribute('href') || '';
        const parts = href.split('/').filter(Boolean);
        // try last segment if it looks like a slug
        const last = parts[parts.length - 1] || '';
        if (last && !last.includes('?') && !last.includes('#')) return last;
      } catch {}
    }
    return '';
  }

  function isMissingIdentifier(s) {
    return !s || s === 'null' || s === 'None' || s === 'undefined';
  }

  function quickAction(action, slug, name, el) {
    // Normalize/derive identifier if needed
    if (isMissingIdentifier(slug)) {
      const derived = resolveIdentifierFromDOM(el || document.activeElement);
      if (derived) slug = derived;
    }
    const label = action.charAt(0).toUpperCase() + action.slice(1);
    if (!confirm(`${label} "${name || ''}"?`)) return;
    callModerationAPI(action, slug, {});
  }

  function callModerationAPI(action, slug, payload) {
    const meta = document.querySelector('meta[name="csrf-token"]');
    const csrf = meta ? meta.getAttribute('content') : '';
    const url  = `/events/admin/${slug}/${action}`;

    fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: Object.assign(
        { 'Content-Type': 'application/json' },
        csrf ? { 'X-CSRFToken': csrf } : {}
      ),
      body: JSON.stringify(payload || {})
    })
    .then(async (r) => {
      const ct = r.headers.get('content-type') || '';
      let data = null;
      if (ct.includes('application/json')) {
        try { data = await r.json(); } catch (e) {}
      } else {
        await r.text();
        showToast('Unexpected response. If you were logged out, please sign in again.', 'error');
        return;
      }
      if (data && data.success) {
        showToast(data.message || `${action} successful`, 'success');
        setTimeout(() => {
          const row = document.getElementById(`row-${slug}`);
          if (row) {
            row.style.transition = 'opacity .4s, transform .4s';
            row.style.opacity = '0';
            row.style.transform = 'translateX(20px)';
            setTimeout(() => row.remove(), 400);
          } else {
            location.reload();
          }
        }, 800);
      } else {
        showToast((data && (data.error || data.message)) || `Failed: ${action}`, 'error');
      }
    })
    .catch(() => showToast('Network error — please try again', 'error'));
  }

  function bindInlineHandlersFallback() {
    // Convert buttons with inline onclick into proper listeners (so CSP can block inline safely)
    document.querySelectorAll('[onclick^="quickAction("]').forEach(el => {
      const attr = el.getAttribute('onclick');
      const args = parseArgsFromOnclick(attr); // [action, slug, name]
      const action = (args[0] || '').replace(/^['"]|['"]$/g, '');
      const slug   = (args[1] || '').replace(/^['"]|['"]$/g, '');
      const name   = (args[2] || '').replace(/^['"]|['"]$/g, '');
      el.addEventListener('click', (e) => {
        e.preventDefault();
        quickAction(action, slug, name, el);
      });
    });

    document.querySelectorAll('[onclick^="openModal("]').forEach(el => {
      const attr = el.getAttribute('onclick');
      const args = parseArgsFromOnclick(attr); // [action, slug, name]
      const action = (args[0] || '').replace(/^['"]|['"]$/g, '');
      let slug   = (args[1] || '').replace(/^['"]|['"]$/g, '');
      const name   = (args[2] || '').replace(/^['"]|['"]$/g, '');
      el.addEventListener('click', (e) => {
        e.preventDefault();
        if (isMissingIdentifier(slug)) {
          const derived = resolveIdentifierFromDOM(el);
          if (derived) slug = derived;
        }
        if (isMissingIdentifier(slug)) {
          showToast('Could not determine event identifier for this row.', 'error');
          return;
        }
        openModal(action, slug, name);
      });
    });

    // Modal close and submit buttons
    document.querySelectorAll('[onclick^="closeModal("]').forEach(el => {
      const args = parseArgsFromOnclick(el.getAttribute('onclick'));
      const action = (args[0] || '').replace(/^['"]|['"]$/g, '');
      el.addEventListener('click', (e) => { e.preventDefault(); closeModal(action); });
    });
    document.querySelectorAll('[onclick^="submitModal("]').forEach(el => {
      const args = parseArgsFromOnclick(el.getAttribute('onclick'));
      const action = (args[0] || '').replace(/^['"]|['"]$/g, '');
      el.addEventListener('click', (e) => { e.preventDefault(); submitModal(action); });
    });
  }

  function wireGlobalUX() {
    // Overlay click to close
    document.querySelectorAll('.mod-overlay').forEach(o => {
      o.addEventListener('click', e => { if (e.target === o) { o.classList.remove('open'); _modalSlug = null; } });
    });
    // Escape to close any open overlays
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') {
        document.querySelectorAll('.mod-overlay.open').forEach(o => o.classList.remove('open'));
        _modalSlug = null;
      }
    });
    // Live clock if present
    const timeEl = document.getElementById('live-time');
    if (timeEl) {
      const tick = () => {
        timeEl.textContent = new Date().toLocaleTimeString('en-GB', {hour12: false});
        setTimeout(tick, 1000);
      };
      tick();
    }
  }

  document.addEventListener('DOMContentLoaded', function(){
    wireGlobalUX();
    bindInlineHandlersFallback();
    // Ensure shake keyframes exist (some templates previously injected via inline script)
    const hasShake = Array.from(document.styleSheets).some(ss => {
      try {
        const rules = ss.cssRules || ss.rules || [];
        return Array.from(rules).some(r => r.name === 'shake');
      } catch (e) { return false; }
    });
    if (!hasShake) {
      const style = document.createElement('style');
      style.textContent = '@keyframes shake { 0%,100%{transform:none} 20%,60%{transform:translateX(-6px)} 40%,80%{transform:translateX(6px)} }';
      document.head.appendChild(style);
    }
  });
})();
