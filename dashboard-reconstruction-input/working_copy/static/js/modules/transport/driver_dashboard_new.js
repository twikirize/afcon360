/**
 * AFCON360 Driver Dashboard New — Modern Uber/Bolt/DiDi Style
 * Vanilla ES6, no jQuery, CSP-compatible
 * Fixed: DriverMap is an object with init() method, not a constructor
 */
(function() {
  'use strict';

  // ==========================================
  // STATE & CONFIG
  // ==========================================
  const state = {
    currentPanel: 'home',
    isOnline: false,
    driverId: null,
    csrfToken: null,
    pingInterval: 30000,
    map: null,
    sheetState: 'peeking',
    sheetDragStartY: 0,
    sheetDragStartHeight: 0,
    isDraggingSheet: false
  };

  const els = {};

  function cacheElements() {
    els.shell = document.getElementById('ddShell');
    els.pane = document.getElementById('ddPane');
    els.overlay = document.getElementById('ddOverlay');
    els.hamburger = document.getElementById('ddHamburger');
    els.paneClose = document.getElementById('ddPaneClose');
    els.paneItems = document.querySelectorAll('.dd-pane-item[data-panel]');
    els.dockItems = document.querySelectorAll('.dd-dock-item[data-panel]');
    els.panels = document.querySelectorAll('.dd-panel[data-panel]');
    els.onlineToggle = document.getElementById('ddOnlineToggle');
    els.onlineLabel = document.getElementById('ddOnlineLabel');
    els.sheet = document.getElementById('ddSheet');
    els.sheetHandle = document.getElementById('ddSheetHandle');
    els.sheetToggle = document.getElementById('ddSheetToggle');
    els.sheetOnlineToggle = document.getElementById('ddSheetOnlineToggle');
    els.navigateBtn = document.getElementById('ddNavigateBtn');
    els.supportBtnSheet = document.getElementById('ddSupportBtnSheet');
    els.safetyBtn = document.getElementById('ddSafetyBtn');
    els.supportBtn = document.getElementById('ddSupportBtn');
    els.closeSafetyModal = document.getElementById('ddCloseSafetyModal');
    els.closeSupportModal = document.getElementById('ddCloseSupportModal');
    els.safetyModal = document.getElementById('ddSafetyModal');
    els.supportModal = document.getElementById('ddSupportModal');
    els.emergencyBtn = document.getElementById('ddEmergencyBtn');
    els.shareTripBtn = document.getElementById('ddShareTripBtn');
    els.goOnlineCta = document.getElementById('ddGoOnlineCta');
    els.editProfileBtn = document.getElementById('ddEditProfileBtn');
    els.settingsBtn = document.getElementById('ddSettingsBtn');
    els.logoutBtn = document.getElementById('ddLogoutBtn');
    els.logoutBtn2 = document.getElementById('ddLogoutBtn2');
    els.editVehicleBtn = document.getElementById('ddEditVehicleBtn');
    els.chatSupportBtn = document.getElementById('ddChatSupportBtn');
  }

  // ==========================================
  // UTILITIES
  // ==========================================
  function csrfHeaders() {
    return { 'Content-Type': 'application/json', 'X-CSRFToken': state.csrfToken };
  }

  function flashMsg(msg, ok = true) {
    const box = document.createElement('div');
    box.className = 'dd-alert ' + (ok ? 'dd-alert-success' : 'dd-alert-error');
    box.style.margin = '0 16px 16px';
    box.innerHTML = '<i class="fa-solid fa-' + (ok ? 'circle-check' : 'circle-exclamation') + '"></i><span style="flex:1;">' + msg + '</span><button onclick="this.parentElement.remove()" class="dd-alert-close"><i class="fa-solid fa-xmark"></i></button>';
    const main = document.querySelector('.dd-main');
    if (main) main.prepend(box);
    setTimeout(() => box.remove(), 5000);
  }

  function fetchWithTimeout(url, options, timeout = 20000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    options = options || {};
    options.signal = controller.signal;
    return fetch(url, options).then(r => { clearTimeout(timer); return r; }, err => { clearTimeout(timer); throw err; });
  }

  // ==========================================
  // PANEL NAVIGATION
  // ==========================================
  function showPanel(panelName) {
    if (!panelName || panelName === state.currentPanel) return;
    els.panels.forEach(p => { const isActive = p.dataset.panel === panelName; p.classList.toggle('active', isActive); p.setAttribute('aria-hidden', !isActive); });
    els.paneItems.forEach(btn => { btn.classList.toggle('active', btn.dataset.panel === panelName); btn.setAttribute('aria-current', btn.dataset.panel === panelName ? 'page' : 'false'); });
    els.dockItems.forEach(btn => { btn.classList.toggle('active', btn.dataset.panel === panelName); });
    state.currentPanel = panelName;
    if (panelName === 'home' && state.map && state.map.map) { setTimeout(() => state.map.map.resize(), 100); }
    closeMobilePane();
  }

  function bindPanelNavigation() {
    els.paneItems.forEach(btn => { btn.addEventListener('click', e => { e.preventDefault(); showPanel(btn.dataset.panel); }); });
    els.dockItems.forEach(btn => { btn.addEventListener('click', e => { e.preventDefault(); showPanel(btn.dataset.panel); }); });
  }

  // ==========================================
  // MOBILE PANE
  // ==========================================
  function openMobilePane() { els.pane.classList.add('open'); els.overlay.classList.add('visible'); els.hamburger.setAttribute('aria-expanded', 'true'); document.body.style.overflow = 'hidden'; }
  function closeMobilePane() { els.pane.classList.remove('open'); els.overlay.classList.remove('visible'); els.hamburger.setAttribute('aria-expanded', 'false'); document.body.style.overflow = ''; }
  function bindMobilePane() {
    els.hamburger.addEventListener('click', openMobilePane);
    els.paneClose.addEventListener('click', closeMobilePane);
    els.overlay.addEventListener('click', closeMobilePane);
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && els.pane.classList.contains('open')) closeMobilePane(); });
  }

  // ==========================================
  // BOTTOM SHEET DRAG
  // ==========================================
  function initBottomSheet() {
    if (!els.sheet || !els.sheetHandle) return;
    const handleDragStart = (clientY) => { state.isDraggingSheet = true; state.sheetDragStartY = clientY; state.sheetDragStartHeight = els.sheet.offsetHeight; els.sheet.classList.remove('peeking', 'expanded'); document.body.style.userSelect = 'none'; };
    const handleDragMove = (clientY) => { if (!state.isDraggingSheet) return; const delta = state.sheetDragStartY - clientY; const maxH = window.innerHeight * 0.85; const minH = 100; let newH = Math.min(maxH, Math.max(minH, state.sheetDragStartHeight + delta)); els.sheet.style.maxHeight = newH + 'px'; };
    const handleDragEnd = () => { if (!state.isDraggingSheet) return; state.isDraggingSheet = false; document.body.style.userSelect = ''; const h = els.sheet.offsetHeight; const midpoint = window.innerHeight * 0.4; if (h < midpoint) { els.sheet.classList.add('peeking'); els.sheet.classList.remove('expanded'); els.sheet.style.maxHeight = '100px'; state.sheetState = 'peeking'; } else { els.sheet.classList.add('expanded'); els.sheet.classList.remove('peeking'); els.sheet.style.maxHeight = '65vh'; state.sheetState = 'expanded'; } setTimeout(() => { els.sheet.style.maxHeight = ''; }, 300); };
    els.sheetHandle.addEventListener('mousedown', e => { e.preventDefault(); handleDragStart(e.clientY); document.addEventListener('mousemove', onMouseMove); document.addEventListener('mouseup', onMouseUp); });
    els.sheetHandle.addEventListener('touchstart', e => { handleDragStart(e.touches[0].clientY); document.addEventListener('touchmove', onTouchMove, { passive: true }); document.addEventListener('touchend', onTouchEnd); }, { passive: true });
    function onMouseMove(e) { handleDragMove(e.clientY); }
    function onMouseUp() { document.removeEventListener('mousemove', onMouseMove); document.removeEventListener('mouseup', onMouseUp); handleDragEnd(); }
    function onTouchMove(e) { handleDragMove(e.touches[0].clientY); }
    function onTouchEnd() { document.removeEventListener('touchmove', onTouchMove); document.removeEventListener('touchend', onTouchEnd); handleDragEnd(); }
    els.sheetHandle.addEventListener('click', e => { if (state.isDraggingSheet) return; toggleSheet(); });
  }
  function toggleSheet() { if (state.sheetState === 'peeking') expandSheet(); else peekSheet(); }
  function expandSheet() { els.sheet.classList.remove('peeking'); els.sheet.classList.add('expanded'); state.sheetState = 'expanded'; }
  function peekSheet() { els.sheet.classList.remove('expanded'); els.sheet.classList.add('peeking'); state.sheetState = 'peeking'; }

  // ==========================================
  // ONLINE TOGGLE
  // ==========================================
  async function handleOnlineToggle(checked, source = 'toggle') {
    const url = els.onlineToggle?.dataset.url || (state.driverId ? '/api/transport/drivers/' + state.driverId + '/status' : null);
    if (!url) { resetToggles(!checked); return; }
    try {
      const res = await fetchWithTimeout(url, { method: 'POST', headers: csrfHeaders(), body: JSON.stringify({ is_online: checked }) });
      const data = await res.json();
      if (data.success) {
        state.isOnline = checked;
        updateOnlineUI(checked);
        if (source === 'toggle' && checked) setTimeout(() => location.reload(), 1200);
      } else { resetToggles(!checked); let msg = data.error || 'Failed to update status'; if (data.go_live && data.go_live.ready === false) msg = 'Complete the go-live requirements before going online'; flashMsg(msg, false); }
    } catch (err) { console.error('Online toggle error:', err); resetToggles(!checked); flashMsg('Network error. Please try again.', false); }
  }
  function updateOnlineUI(online) {
    const label = online ? 'Online' : 'Offline';
    const badgeText = online ? 'Receiving rides' : 'Tap to go online';
    const badgeClass = online ? 'dd-btn-primary' : 'dd-btn-warning';
    if (els.onlineLabel) els.onlineLabel.textContent = label;
    if (els.sheetOnlineToggle) els.sheetOnlineToggle.checked = online;
    if (els.sheetToggle) { els.sheetToggle.className = 'dd-btn dd-btn-block dd-sheet-toggle ' + (online ? 'dd-btn-primary' : 'dd-btn-warning'); const small = els.sheetToggle.querySelector('small'); if (small) small.textContent = online ? 'Tap to go offline' : 'Tap to start receiving rides'; }
    const heroBadge = document.querySelector('.dd-hero-status .dd-btn, .dd-hero-status .badge'); if (heroBadge) { heroBadge.textContent = badgeText; heroBadge.className = 'dd-btn dd-btn-sm ' + badgeClass; }
  }
  function resetToggles(checked) { if (els.onlineToggle) els.onlineToggle.checked = checked; if (els.sheetOnlineToggle) els.sheetOnlineToggle.checked = checked; }
  function bindOnlineToggle() {
    if (els.onlineToggle) els.onlineToggle.addEventListener('change', () => handleOnlineToggle(els.onlineToggle.checked, 'toggle'));
    if (els.sheetOnlineToggle) els.sheetOnlineToggle.addEventListener('change', () => handleOnlineToggle(els.sheetOnlineToggle.checked, 'sheet'));
    if (els.sheetToggle) els.sheetToggle.addEventListener('click', () => { const newState = !els.sheetOnlineToggle.checked; els.sheetOnlineToggle.checked = newState; handleOnlineToggle(newState, 'sheet'); });
    if (els.goOnlineCta) els.goOnlineCta.addEventListener('click', () => { if (els.onlineToggle) { els.onlineToggle.checked = true; handleOnlineToggle(true, 'cta'); } });
  }

  // ==========================================
  // MODALS
  // ==========================================
  function openModal(modal) { modal.classList.add('open'); document.body.style.overflow = 'hidden'; modal.querySelector('.dd-modal-close')?.focus(); }
  function closeModal(modal) { modal.classList.remove('open'); document.body.style.overflow = ''; }
  function bindModals() {
    els.safetyBtn?.addEventListener('click', () => openModal(els.safetyModal));
    els.closeSafetyModal?.addEventListener('click', () => closeModal(els.safetyModal));
    els.supportBtn?.addEventListener('click', () => openModal(els.supportModal));
    els.supportBtnSheet?.addEventListener('click', () => openModal(els.supportModal));
    els.closeSupportModal?.addEventListener('click', () => closeModal(els.supportModal));
    [els.safetyModal, els.supportModal].forEach(modal => { modal?.addEventListener('click', e => { if (e.target === modal || e.target.classList.contains('dd-modal-backdrop')) closeModal(modal); }); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') { if (els.safetyModal.classList.contains('open')) closeModal(els.safetyModal); if (els.supportModal.classList.contains('open')) closeModal(els.supportModal); } });
    els.emergencyBtn?.addEventListener('click', () => { if (confirm('Call emergency services (999)?')) window.location.href = 'tel:999'; });
    els.shareTripBtn?.addEventListener('click', async () => { if (!state.driverId) return flashMsg('Driver ID not found', false); try { const res = await fetchWithTimeout('/transport/api/drivers/' + state.driverId + '/share-trip', { method: 'POST', headers: csrfHeaders() }); const data = await res.json(); if (data.success && data.share_url) { if (navigator.share) await navigator.share({ title: 'My Trip', text: 'Tracking my ride', url: data.share_url }); else { await navigator.clipboard.writeText(data.share_url); flashMsg('Trip link copied to clipboard', true); } } else flashMsg(data.message || 'Could not create share link', false); } catch (err) { console.error(err); flashMsg('Failed to share trip', false); } });
  }

  // ==========================================
  // MAP INITIALIZATION (FIXED: DriverMap is object with init())
  // ==========================================
  async function initMap() {
    const container = document.getElementById('ddMap');
    if (!container || container.dataset.mapInitialized) return;
    container.dataset.mapInitialized = 'true';
    if (typeof DriverMap === 'undefined') { let attempts = 0; while (typeof DriverMap === 'undefined' && attempts < 100) { await new Promise(r => setTimeout(r, 100)); attempts++; } }
    if (typeof DriverMap !== 'undefined') {
      try {
        // DriverMap is an object with init() method, not a constructor
        state.map = Object.create(DriverMap);
        await state.map.init('ddMap');
        console.log('[DriverDashboard] Map initialized');
      } catch (err) { console.error('[DriverDashboard] Map init failed:', err); }
    } else { console.warn('[DriverDashboard] DriverMap not available after waiting'); }
  }

  // ==========================================
  // LOCATION PING
  // ==========================================
  function startLocationPing() {
    if (!navigator.geolocation) return;
    const ping = () => { if (state.isOnline) { navigator.geolocation.getCurrentPosition(pos => { fetchWithTimeout('/transport/api/drivers/location', { method: 'POST', headers: csrfHeaders(), body: JSON.stringify({ latitude: pos.coords.latitude, longitude: pos.coords.longitude, accuracy: pos.coords.accuracy }) }).catch(console.error); }, console.error, { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }); } };
    setInterval(ping, state.pingInterval);
    if (state.isOnline) ping();
  }

  // ==========================================
  // INITIALIZATION
  // ==========================================
  function init() {
    const dashboard = document.getElementById('ddShell');
    if (dashboard) { state.driverId = dashboard.dataset.driverId || null; state.csrfToken = dashboard.dataset.csrf || null; state.pingInterval = parseInt(dashboard.dataset.pingInterval || '30000', 10); state.isOnline = dashboard.dataset.isOnline === '1'; }
    cacheElements();
    bindPanelNavigation();
    bindMobilePane();
    initBottomSheet();
    bindOnlineToggle();
    bindModals();
    initMap();
    startLocationPing();
    showPanel('home');
    window.__ddDashboard = { showPanel, state, map: () => state.map };
    console.log('[DriverDashboard] Initialized v1.1');
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();