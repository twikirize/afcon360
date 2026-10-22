/*
 * AFCON360 — Owner Backup & Restore UI
 * static/js/owner/backups.js
 *
 * CSP: loaded as an external script from 'self' (no inline script block, no
 * inline event handlers). All interactivity is bound through data-attributes
 * and event delegation in this file.
 *
 * Endpoints are read from data-attributes rendered by the template so this
 * file never needs server-side templating.
 */
(function () {
  'use strict';

  var root = document.getElementById('bkRoot');
  if (!root) {
    return;
  }

  var ENDPOINTS = {
    create: root.dataset.createUrl,
    progress: root.dataset.progressUrl,          // contains __ID__ placeholder
    cancel: root.dataset.cancelUrl,              // contains __ID__ placeholder
    restore: root.dataset.restoreUrl             // contains __ID__ placeholder
  };

  var state = {
    backupId: null,
    pollTimer: null,
    elapsedTimer: null,
    startedAt: null,
    lastDetailCount: 0
  };

  function $(id) {
    return document.getElementById(id);
  }

  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) {
      return meta.content;
    }
    var input = document.querySelector('input[name="csrf_token"]');
    return input ? input.value : '';
  }

  function formatElapsed(seconds) {
    var s = Math.max(0, Math.floor(seconds || 0));
    var m = Math.floor(s / 60);
    var h = Math.floor(m / 60);
    var rem = s % 60;
    if (h > 0) {
      return h + 'h ' + String(m % 60).padStart(2, '0') + 'm ' + String(rem).padStart(2, '0') + 's';
    }
    if (m > 0) {
      return m + 'm ' + String(rem).padStart(2, '0') + 's';
    }
    return rem + 's';
  }

  function setText(id, value) {
    var el = $(id);
    if (el) {
      el.textContent = value == null ? '' : value;
    }
  }

  /*
   * Build a URL from a template rendered by the server. The template uses
   * `__ID__` as the placeholder because braces would be percent-encoded by
   * url_for. `{id}` is also accepted for robustness.
   */
  function buildUrl(template, id) {
    if (!template) {
      return '';
    }
    var encoded = encodeURIComponent(id);
    return template.replace('__ID__', encoded).replace('{id}', encoded);
  }

  /* ------------------------------------------------------------------ */
  /* Progress modal visibility                                           */
  /* ------------------------------------------------------------------ */
  function showProgressModal() {
    var modal = $('progressModal');
    if (!modal) {
      return;
    }
    modal.style.display = 'flex';
    var bar = $('progressBar');
    if (bar) {
      bar.style.width = '0%';
      bar.style.background = '#4f46e5';
    }
    setText('progressStep', 'Starting…');
    setText('progressSubstep', '');
    setText('progressDetail', '');
    setText('progressElapsed', '0s');
    setText('progressLog', '');
    state.startedAt = Date.now();
    state.lastDetailCount = 0;
    setControlButtonsState(true);
    startElapsedTicker();
  }

  function hideProgressModal() {
    var modal = $('progressModal');
    if (modal) {
      modal.style.display = 'none';
    }
    stopPolling();
  }

  function startElapsedTicker() {
    stopElapsedTicker();
    state.elapsedTimer = window.setInterval(function () {
      if (!state.startedAt) {
        return;
      }
      setText('progressElapsed', formatElapsed((Date.now() - state.startedAt) / 1000));
    }, 500);
  }

  function stopElapsedTicker() {
    if (state.elapsedTimer) {
      window.clearInterval(state.elapsedTimer);
      state.elapsedTimer = null;
    }
  }

  /* ------------------------------------------------------------------ */
  /* Backup start                                                        */
  /* ------------------------------------------------------------------ */
  function startBackup(button) {
    var typeSelect = $('backupTypeSelect');
    var backupType = typeSelect ? typeSelect.value : 'database';

    if (button) {
      button.disabled = true;
      button.innerHTML = '<i class="bi bi-hourglass-split"></i> Starting…';
    }

    fetch(ENDPOINTS.create, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-CSRFToken': csrfToken()
      },
      body: new URLSearchParams({ backup_type: backupType, csrf_token: csrfToken() })
    })
      .then(function (r) {
        if (!r.ok) {
          throw new Error('HTTP ' + r.status);
        }
        return r.json();
      })
      .then(function (data) {
        if (data && data.backup_id) {
          state.backupId = data.backup_id;
          showProgressModal();
          // The durable record is committed before the worker thread starts,
          // so refreshing here makes the in-progress entry visible in the
          // history list instead of leaving it empty for the whole run.
          refreshHistory();
          pollProgress(data.backup_id);
        } else {
          window.alert('Failed to start backup: ' + ((data && data.error) || 'Unknown error'));
        }
      })
      .catch(function (err) {
        console.error('[backup] start failed', err);
        window.alert('Error starting backup: ' + err.message);
      })
      .finally(function () {
        if (button) {
          button.disabled = false;
          button.innerHTML = '<i class="bi bi-cloud-upload"></i> Create Backup';
        }
      });
  }

  /* ------------------------------------------------------------------ */
  /* Progress polling                                                    */
  /* ------------------------------------------------------------------ */
  function pollProgress(backupId) {
    stopPolling();
    var url = buildUrl(ENDPOINTS.progress, backupId);

    var tick = function () {
      fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
        .then(function (r) { return r.json(); })
        .then(function (payload) {
          if (!payload) {
            return;
          }
          if (payload.error && payload.finished === undefined) {
            setText('progressStep', payload.error);
            stopPolling();
            return;
          }
          updateProgressUI(payload);
          if (payload.finished) {
            stopPolling();
            stopElapsedTicker();
            setControlButtonsState(false);
            refreshHistory();
          }
        })
        .catch(function (err) {
          console.error('[backup] poll failed', err);
        });
    };

    tick();
    state.pollTimer = window.setInterval(tick, 1000);
  }

  function stopPolling() {
    if (state.pollTimer) {
      window.clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
  }

  function updateProgressUI(payload) {
    var pct = Math.max(0, Math.min(100, Number(payload.progress) || 0));
    var bar = $('progressBar');
    if (bar) {
      bar.style.width = pct + '%';
    }

    setText('progressStep', payload.step || 'Working…');
    setText('progressSubstep', payload.substep || '');
    setText('progressDetail', payload.error ? payload.error : '');
    setText('progressElapsed', formatElapsed(payload.elapsed));

    var details = payload.details || [];
    if (details.length !== state.lastDetailCount) {
      state.lastDetailCount = details.length;
      var log = $('progressLog');
      if (log) {
        log.textContent = details.slice(-8).join('\n');
      }
    }

    if (payload.finished) {
      var barEl = $('progressBar');
      if (barEl) {
        if (payload.cancelled) {
          barEl.style.background = '#d97706';
        } else {
          barEl.style.background = payload.error ? '#dc2626' : '#16a34a';
        }
      }
    }
  }

  function setControlButtonsState(running) {
    var cancel = $('btnCancel');
    if (cancel) {
      cancel.disabled = !running;
    }
    var close = $('btnCloseProgress');
    if (close) {
      close.disabled = running;
    }
  }

  /* ------------------------------------------------------------------ */
  /* Cancel                                                              */
  /* ------------------------------------------------------------------ */
  function cancelBackup() {
    if (!state.backupId) {
      return;
    }
    var url = buildUrl(ENDPOINTS.cancel, state.backupId);
    fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-CSRFToken': csrfToken()
      },
      body: new URLSearchParams({ csrf_token: csrfToken() })
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data && data.error) {
          setText('progressDetail', data.error);
        } else {
          setText('progressStep', 'Cancelling…');
        }
      })
      .catch(function (err) {
        console.error('[backup] cancel failed', err);
        setText('progressDetail', 'Cancel request failed: ' + err.message);
      });
  }

  /* ------------------------------------------------------------------ */
  /* History refresh                                                     */
  /* ------------------------------------------------------------------ */
  function refreshHistory() {
    var container = $('backupHistory');
    if (!container) {
      return;
    }
    fetch(window.location.href, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        if (!html) {
          return;
        }
        var doc = new DOMParser().parseFromString(html, 'text/html');
        var fresh = doc.getElementById('backupHistory');
        if (fresh) {
          container.innerHTML = fresh.innerHTML;
        }
      })
      .catch(function (err) {
        console.error('[backup] history refresh failed', err);
      });
  }

  /* ------------------------------------------------------------------ */
  /* Restore modal                                                       */
  /* ------------------------------------------------------------------ */
  function openRestore(publicId) {
    var form = $('restoreForm');
    var modal = $('restoreModal');
    if (!form || !modal) {
      return;
    }
    form.action = buildUrl(ENDPOINTS.restore, publicId);
    modal.style.display = 'flex';
  }

  function closeRestore() {
    var modal = $('restoreModal');
    if (modal) {
      modal.style.display = 'none';
    }
  }

  /* ------------------------------------------------------------------ */
  /* Event delegation — no inline handlers anywhere in the markup       */
  /* ------------------------------------------------------------------ */
  document.addEventListener('click', function (ev) {
    var target = ev.target.closest('[data-bk-action]');
    if (!target) {
      // Click-away handling for the restore modal.
      var restoreModal = $('restoreModal');
      if (restoreModal && ev.target === restoreModal) {
        closeRestore();
      }
      return;
    }

    var action = target.dataset.bkAction;

    if (action === 'start-backup') {
      ev.preventDefault();
      startBackup(target);
    } else if (action === 'cancel-backup') {
      ev.preventDefault();
      cancelBackup();
    } else if (action === 'close-progress') {
      ev.preventDefault();
      stopPolling();
      stopElapsedTicker();
      hideProgressModal();
      state.backupId = null;
      window.location.reload();
    } else if (action === 'open-restore') {
      ev.preventDefault();
      openRestore(target.dataset.publicId);
    } else if (action === 'close-restore') {
      ev.preventDefault();
      closeRestore();
    }
  });

  // Confirm-guarded destructive submits.
  document.addEventListener('submit', function (ev) {
    var form = ev.target;
    var message = form && form.getAttribute ? form.getAttribute('data-bk-confirm') : null;
    if (message && !window.confirm(message)) {
      ev.preventDefault();
    }
  });

  // Expose a minimal surface for debugging from the console.
  window.AFCON360Backups = {
    start: startBackup,
    cancel: cancelBackup,
    refreshHistory: refreshHistory,
    state: state
  };
})();
