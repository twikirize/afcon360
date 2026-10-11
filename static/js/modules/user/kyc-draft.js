/**
 * AFCON360 KYC Draft Autosave
 *
 * Client-only draft persistence for the KYC upload form so a user can leave and
 * come back later (even after logging out) without losing progress — as long as
 * the same device/browser is used.
 *
 * Design constraints (approved):
 * - Storage: browser IndexedDB only. No KYC data is sent to the server until the
 *   normal form submit.
 * - Device binding: a random device id kept in a first-party cookie
 *   (SameSite=Lax, Path=/). A draft is restored only when the cookie matches the
 *   id stored with the draft; a missing/mismatched cookie means "device changed"
 *   and the draft is discarded.
 * - Lifetime: 7 days from the last save.
 *
 * Public API (window.KycDraft):
 *   attach(form, { key })  -> controller { save(), clear(), destroy() }
 *   clear(key)
 *   markSubmitted(key)     -> flag a successful final submit for the next page
 *   resolvePendingOnLoad() -> on a post-submit page, clear the draft if flagged
 */
(function (global) {
  'use strict';

  var DB_NAME = 'afcon360_kyc_draft';
  var DB_VERSION = 1;
  var STORE = 'drafts';
  var DEVICE_COOKIE = 'afcon_kyc_device';
  var SUBMIT_FLAG = 'kyc_draft_submitted_key';
  var TTL_MS = 7 * 24 * 60 * 60 * 1000;
  var DEBOUNCE_MS = 700;
  // Never persist session/sensitive transport fields in a draft.
  var EXCLUDED_FIELDS = ['csrf_token', 'reupload_token', 'selfie_pair_nonce'];

  function nowMs() {
    return Date.now();
  }

  function readCookie(name) {
    var parts = document.cookie ? document.cookie.split('; ') : [];
    for (var i = 0; i < parts.length; i++) {
      var eq = parts[i].indexOf('=');
      if (eq > -1 && parts[i].slice(0, eq) === name) {
        return decodeURIComponent(parts[i].slice(eq + 1));
      }
    }
    return null;
  }

  function writeCookie(name, value, maxAgeSeconds) {
    document.cookie =
      name + '=' + encodeURIComponent(value) +
      '; Max-Age=' + maxAgeSeconds +
      '; Path=/; SameSite=Lax';
  }

  function deviceId() {
    var id = readCookie(DEVICE_COOKIE);
    if (!id) {
      id = (global.crypto && typeof global.crypto.randomUUID === 'function')
        ? global.crypto.randomUUID()
        : 'dev-' + nowMs() + '-' + Math.random().toString(36).slice(2);
      writeCookie(DEVICE_COOKIE, id, Math.floor(TTL_MS / 1000));
    }
    return id;
  }

  function openDb() {
    return new Promise(function (resolve, reject) {
      if (!global.indexedDB) {
        reject(new Error('IndexedDB unavailable'));
        return;
      }
      var req = global.indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = function () {
        var db = req.result;
        if (!db.objectStoreNames.contains(STORE)) {
          db.createObjectStore(STORE, { keyPath: 'key' });
        }
      };
      req.onsuccess = function () { resolve(req.result); };
      req.onerror = function () { reject(req.error); };
    });
  }

  function idbPut(record) {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, 'readwrite');
        tx.objectStore(STORE).put(record);
        tx.oncomplete = function () { resolve(); };
        tx.onerror = function () { reject(tx.error); };
        tx.onabort = function () { reject(tx.error); };
      });
    });
  }

  function idbGet(key) {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, 'readonly');
        var req = tx.objectStore(STORE).get(key);
        req.onsuccess = function () { resolve(req.result || null); };
        req.onerror = function () { reject(req.error); };
      });
    });
  }

  function idbDelete(key) {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, 'readwrite');
        tx.objectStore(STORE).delete(key);
        tx.oncomplete = function () { resolve(); };
        tx.onerror = function () { reject(tx.error); };
      });
    });
  }

  function collect(form) {
    var fields = {};
    var files = [];
    var elements = form.querySelectorAll('input, select, textarea');
    for (var i = 0; i < elements.length; i++) {
      var el = elements[i];
      if (!el.name) continue;
      if (EXCLUDED_FIELDS.indexOf(el.name) !== -1) continue;

      if (el.type === 'file') {
        if (el.files && el.files[0]) {
          files.push({
            name: el.name,
            filename: el.files[0].name,
            type: el.files[0].type,
            blob: el.files[0],
          });
        }
        continue;
      }

      if (el.type === 'checkbox') {
        if (!Object.prototype.hasOwnProperty.call(fields, el.name)) fields[el.name] = [];
        if (el.checked) fields[el.name].push(el.value);
        continue;
      }
      if (el.type === 'radio') {
        if (el.checked) fields[el.name] = el.value;
        continue;
      }
      fields[el.name] = el.value;
    }
    return { fields: fields, files: files };
  }

  function applyFiles(form, files) {
    if (typeof global.DataTransfer !== 'function') return;
    (files || []).forEach(function (f) {
      var input = form.querySelector('input[type="file"][name="' + f.name + '"]');
      if (!input || !f.blob) return;
      try {
        var dt = new DataTransfer();
        dt.items.add(new File([f.blob], f.filename || 'file', { type: f.type || '' }));
        input.files = dt.files;
      } catch (e) {
        // Blob reconstruction unsupported — the field stays empty; text fields
        // are still restored.
      }
    });
  }

  function restore(form, record) {
    var fields = record.fields || {};
    var elements = form.querySelectorAll('input, select, textarea');
    for (var i = 0; i < elements.length; i++) {
      var el = elements[i];
      if (!el.name || el.type === 'file') continue;
      if (!Object.prototype.hasOwnProperty.call(fields, el.name)) continue;
      if (el.type === 'checkbox') {
        var wanted = fields[el.name] || [];
        el.checked = wanted.indexOf(el.value) !== -1;
      } else if (el.type === 'radio') {
        el.checked = (el.value === fields[el.name]);
      } else {
        el.value = fields[el.name];
      }
      el.dispatchEvent(new Event('change', { bubbles: true }));
    }
    applyFiles(form, record.files);
  }

  function clear(key) {
    try {
      global.sessionStorage.removeItem(SUBMIT_FLAG);
    } catch (e) { /* ignore */ }
    return idbDelete(key).catch(function () { /* best effort */ });
  }

  function markSubmitted(key) {
    try {
      global.sessionStorage.setItem(SUBMIT_FLAG, key);
    } catch (e) { /* ignore */ }
  }

  // Read and immediately remove the "final submit" flag without clearing the
  // draft. Used on the upload page: if the flag is present here, the previous
  // submit landed back on the form (i.e. it failed), so the draft must stay.
  function consumeSubmitFlag() {
    var key = null;
    try {
      key = global.sessionStorage.getItem(SUBMIT_FLAG);
      global.sessionStorage.removeItem(SUBMIT_FLAG);
    } catch (e) { /* ignore */ }
    return key;
  }

  function resolvePendingOnLoad() {
    var key = consumeSubmitFlag();
    if (key) clear(key);
  }

  function attach(form, opts) {
    opts = opts || {};
    var key = opts.key || 'individual';
    var saveTimer = null;
    var restoring = false;
    var statusEl = opts.statusEl || null;
    var saveBtn = opts.saveBtn || null;

    function setStatus(text, canDiscard) {
      if (!statusEl) return;
      statusEl.textContent = '';
      var span = document.createElement('span');
      span.className = 'kyc-draft-text';
      span.textContent = text;
      statusEl.appendChild(span);
      if (canDiscard) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'kyc-draft-discard';
        btn.textContent = 'Discard draft';
        btn.addEventListener('click', function () {
          clear(key).then(function () {
            form.reset();
            setStatus('Draft discarded.', false);
          });
        });
        statusEl.appendChild(btn);
      }
      statusEl.style.display = '';
    }

    function save() {
      if (restoring) return Promise.resolve();
      var data = collect(form);
      var record = {
        key: key,
        deviceId: deviceId(),
        savedAt: nowMs(),
        fields: data.fields,
        files: data.files,
      };
      return idbPut(record).then(function () {
        setStatus('Draft saved automatically. You can leave and continue later.', true);
      }).catch(function () { /* best effort; never block the user */ });
    }

    function scheduleSave() {
      if (saveTimer) clearTimeout(saveTimer);
      saveTimer = setTimeout(save, DEBOUNCE_MS);
    }

    // Use the page's existing status element when present; otherwise inject one.
    statusEl = opts.statusEl || form.querySelector('.kyc-draft-status');
    if (!statusEl) {
      statusEl = document.createElement('div');
      statusEl.className = 'kyc-draft-status';
      statusEl.style.display = 'none';
      form.appendChild(statusEl);
    }

    return idbGet(key).then(function (record) {
      if (!record) return;
      if (record.deviceId !== deviceId()) {
        return idbDelete(key);
      }
      if (nowMs() - (record.savedAt || 0) > TTL_MS) {
        return idbDelete(key);
      }
      restoring = true;
      restore(form, record);
      restoring = false;
      setStatus('Draft from your previous visit restored.', true);
      if (typeof opts.onRestored === 'function') opts.onRestored(record);
    }).catch(function () { /* no draft / storage unavailable */ }).then(function () {
      form.addEventListener('input', scheduleSave, true);
      form.addEventListener('change', scheduleSave, true);
      if (saveBtn) {
        saveBtn.addEventListener('click', function () { save(); });
      }
      return {
        save: save,
        clear: function () { return clear(key); },
        key: key,
      };
    });
  }

  global.KycDraft = {
    deviceId: deviceId,
    attach: attach,
    clear: clear,
    markSubmitted: markSubmitted,
    consumeSubmitFlag: consumeSubmitFlag,
    resolvePendingOnLoad: resolvePendingOnLoad,
  };
})(window);
