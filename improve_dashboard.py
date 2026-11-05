with open('templates/transport/driver/driver_dashboard.html', 'r') as f:
    content = f.read()

# ============================================================
# 1. REPLACE THE LOCATION CARD with compact status pill + telemetry grid
# ============================================================
old_location_card = '''  <div class="card ws-card ck-full">
    <div class="card-header">
      <span class="card-title"><i class="fa-solid fa-location-dot"></i> Location</span>
      <span class="badge badge-{{ 'green' if driver_profile.is_online else 'gray' }}">
        {{ 'Publishing' if driver_profile.is_online else 'Idle' }}
      </span>
    </div>
    <div style="padding:16px;">
      <div class="ws-row" style="border-bottom:none;padding-top:0;">
        <span class="ws-k">Last published</span>
        {% if driver_profile.last_location and driver_profile.location_updated_at %}
        <span class="ws-v location-display" data-lat="{{ driver_profile.last_location.get('latitude') }}" data-lng="{{ driver_profile.last_location.get('longitude') }}" data-place="{{ driver_profile.last_location.get('place_name', 'Unknown location') }}">
          <span class="place-name">{{ driver_profile.last_location.get('place_name', 'Loading location...') }}</span>
          <button type="button" class="btn btn-ghost btn-xs coords-toggle" aria-label="Show coordinates" title="Show coordinates">
            <i class="fa-solid fa-map-pin"></i> Coordinates
          </button>
        </span>
        {% else %}
        <span class="ws-v">No location published yet.</span>
        {% endif %}
      </div>
      {% if driver_profile.location_updated_at %}
      <div class="ws-row" style="border-bottom:none;padding-top:0;">
        <span class="ws-k">At</span>
        <span class="ws-v">{{ driver_profile.location_updated_at.strftime('%Y-%m-%d %H:%M:%S') if driver_profile.location_updated_at else '' }}</span>
      </div>
      {% endif %}
      <div id="dcLocBadge" class="dc-toast" role="status" aria-live="polite"></div>
      <div class="ws-row" style="border-bottom:none; margin-top:8px; font-size:0.68rem;">
        <span class="ws-k">GPS</span>
        <span id="dcGpsStatus" class="ws-v dc-toast ok">Initializing…</span>
      </div>
      <div class="ws-row" style="border-bottom:none;">
        <span class="ws-k">Publish</span>
        <span id="dcPublishStatus" class="ws-v dc-toast ok">Idle</span>
      </div>
      <div class="ws-row" style="border-bottom:none;">
        <span class="ws-k">Health</span>
        <span id="dcHealthStatus" class="ws-v dc-toast ok">Unknown</span>
      </div>
      <div class="ws-row" style="border-bottom:none;">
        <span class="ws-k">Auth</span>
        <span id="dcAuthStatus" class="ws-v dc-toast ok">Authenticated</span>
      </div>
      <div class="ws-row" style="border-bottom:none;">
        <span class="ws-k">Network</span>
        <span id="dcNetStatus" class="ws-v dc-toast ok">Online</span>
      </div>
    </div>
  </div>'''

new_location_card = '''  <div class="card ws-card ck-full">
    <div class="card-header">
      <span class="card-title"><i class="fa-solid fa-location-dot"></i> Location</span>
      <span class="status-pill" id="locationStatusPill">
        <span class="status-pill__dot" id="locationStatusDot"></span>
        <span class="status-pill__text" id="locationStatusText">Initializing…</span>
      </span>
    </div>
    <div style="padding:16px;">
      {% if driver_profile.last_location and driver_profile.location_updated_at %}
      <div class="telemetry-grid">
        <div class="telemetry-item">
          <span class="telemetry-label">Place</span>
          <span class="telemetry-value place-name" data-place="{{ driver_profile.last_location.get('place_name', 'Unknown location') }}">
            {{ driver_profile.last_location.get('place_name', 'Loading location...') }}
          </span>
        </div>
        <div class="telemetry-item">
          <span class="telemetry-label">Coordinates</span>
          <span class="telemetry-value coords" data-lat="{{ driver_profile.last_location.get('latitude') }}" data-lng="{{ driver_profile.last_location.get('longitude') }}">
            <span class="coords-hidden">{{ driver_profile.last_location.get('latitude')|round(6) }}, {{ driver_profile.last_location.get('longitude')|round(6) }}</span>
            <button type="button" class="btn btn-ghost btn-xs coords-toggle" aria-label="Show coordinates">
              <i class="fa-solid fa-map-pin"></i> Show
            </button>
          </span>
        </div>
        <div class="telemetry-item">
          <span class="telemetry-label">Updated</span>
          <span class="telemetry-value">{{ driver_profile.location_updated_at.strftime('%Y-%m-%d %H:%M:%S') if driver_profile.location_updated_at else '' }}</span>
        </div>
        <div class="telemetry-item">
          <span class="telemetry-label">Accuracy</span>
          <span class="telemetry-value">{{ '%.0f'|format(driver_profile.last_location.get('accuracy')|float) if driver_profile.last_location.get('accuracy') else '—' }} m</span>
        </div>
      </div>
      {% else %}
      <div class="ws-row" style="border-bottom:none;padding-top:0;">
        <span class="ws-k">Last published</span>
        <span class="ws-v">No location published yet.</span>
      </div>
      {% endif %}
      <div id="dcLocBadge" class="dc-toast" role="status" aria-live="polite"></div>
      <div class="ws-row" style="border-bottom:none; margin-top:8px; font-size:0.68rem;">
        <span class="ws-k">GPS</span>
        <span id="dcGpsStatus" class="ws-v dc-toast ok">Initializing…</span>
      </div>
      <div class="ws-row" style="border-bottom:none;">
        <span class="ws-k">Publish</span>
        <span id="dcPublishStatus" class="ws-v dc-toast ok">Idle</span>
      </div>
    </div>
  </div>'''

if old_location_card in content:
    content = content.replace(old_location_card, new_location_card)
    print('✓ Replaced location card')
else:
    print('✗ Location card not found')

# ============================================================
# 2. REPLACE MAP CARD HEADER - integrate timestamp into map controls
# ============================================================
old_map_card = '''  <div class="card ws-card ck-full driver-location-map">
    <div class="card-header">
      <span class="card-title"><i class="fa-solid fa-map-location-dot"></i> Driver location map</span>
      <span id="driverMapState" class="badge badge-gray" role="status" aria-live="polite">Preparing map…</span>
    </div>'''

new_map_card = '''  <div class="card ws-card ck-full driver-location-map">
    <div class="card-header">
      <span class="card-title"><i class="fa-solid fa-map-location-dot"></i> Driver location map</span>
      {% if driver_profile.last_location and driver_profile.location_updated_at %}
      <span class="map-last-updated" id="mapLastUpdated">
        <i class="fa-solid fa-clock"></i> {{ driver_profile.location_updated_at.strftime('%H:%M:%S') }}
      </span>
      {% else %}
      <span id="driverMapState" class="badge badge-gray" role="status" aria-live="polite">Preparing map…</span>
      {% endif %}
    </div>'''

if old_map_card in content:
    content = content.replace(old_map_card, new_map_card)
    print('✓ Replaced map card header')
else:
    print('✗ Map card header not found')

# ============================================================
# 3. IMPROVE STATUS PANEL - Operational preferences compact grid
# ============================================================
old_status_prefs = '''  <div class="card ws-card">
    <div class="card-header"><span class="card-title"><i class="fa-solid fa-sliders"></i> Operational preferences</span></div>
    <div class="ws-row"><span class="ws-k">Driving mode</span><span class="ws-v">{{ (driver_profile.service_types or ['on_demand'])|join(', ')|replace('_',' ')|title }}</span></div>
    <div class="ws-row"><span class="ws-k">Vehicle classes</span><span class="ws-v">{{ (driver_profile.vehicle_classes or ['comfort'])|join(', ')|replace('_',' ')|title }}</span></div>
    <div class="ws-row"><span class="ws-k">Operational zones</span><span class="ws-v">{{ driver_profile.operational_zones|join(', ') if driver_profile.operational_zones else 'All' }}</span></div>
    <div class="ws-row"><span class="ws-k">Max passengers</span><span class="ws-v">{{ driver_profile.max_passenger_capacity|default(4) }}</span></div>
    <div class="ws-row"><span class="ws-k">Auto-accept bookings</span><span class="ws-v">{{ 'On' if driver_profile.auto_accept_bookings else 'Off' }}</span></div>
    <div class="ws-row" style="border-bottom:none;"><span class="ws-k">Concurrent trips</span><span class="ws-v">{{ driver_profile.max_concurrent_bookings|default(1) }}</span></div>
  </div>'''

new_status_prefs = '''  <div class="card ws-card">
    <div class="card-header"><span class="card-title"><i class="fa-solid fa-sliders"></i> Operational preferences</span></div>
    <div class="prefs-grid">
      <div class="pref-item">
        <span class="pref-label">Driving mode</span>
        <span class="pref-value">{{ (driver_profile.service_types or ['on_demand'])|join(', ')|replace('_',' ')|title }}</span>
      </div>
      <div class="pref-item">
        <span class="pref-label">Vehicle classes</span>
        <span class="pref-value">{{ (driver_profile.vehicle_classes or ['comfort'])|join(', ')|replace('_',' ')|title }}</span>
      </div>
      <div class="pref-item">
        <span class="pref-label">Operational zones</span>
        <span class="pref-value">{{ driver_profile.operational_zones|join(', ') if driver_profile.operational_zones else 'All' }}</span>
      </div>
      <div class="pref-item">
        <span class="pref-label">Max passengers</span>
        <span class="pref-value">{{ driver_profile.max_passenger_capacity|default(4) }}</span>
      </div>
      <div class="pref-item">
        <span class="pref-label">Auto-accept bookings</span>
        <span class="pref-value">{{ 'On' if driver_profile.auto_accept_bookings else 'Off' }}</span>
      </div>
      <div class="pref-item">
        <span class="pref-label">Concurrent trips</span>
        <span class="pref-value">{{ driver_profile.max_concurrent_bookings|default(1) }}</span>
      </div>
    </div>
  </div>'''

if old_status_prefs in content:
    content = content.replace(old_status_prefs, new_status_prefs)
    print('✓ Replaced status panel preferences')
else:
    print('✗ Status panel preferences not found')

# ============================================================
# 4. ADD CSS for new components
# ============================================================
css_injection = '''
  <style nonce="{{ csp_nonce }}">
    /* Status Pill */
    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 0.7rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }
    .status-pill__dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--text-muted);
    }
    .status-pill--online .status-pill__dot { background: var(--green); box-shadow: 0 0 6px var(--green); }
    .status-pill--publishing .status-pill__dot { background: var(--blue); box-shadow: 0 0 6px var(--blue); }
    .status-pill--offline .status-pill__dot { background: var(--text-muted); }
    .status-pill--error .status-pill__dot { background: var(--red); box-shadow: 0 0 6px var(--red); }

    /* Telemetry Grid */
    .telemetry-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 12px;
      margin-bottom: 8px;
    }
    .telemetry-item {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    .telemetry-label {
      font-size: 0.6rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      font-weight: 600;
    }
    .telemetry-value {
      font-size: 0.8rem;
      font-family: var(--font-mono);
      color: var(--text);
    }
    .telemetry-value .place-name { font-family: var(--font-sans); }
    .telemetry-value .coords-hidden { display: none; }
    .telemetry-value .coords-toggle { margin-left: 8px; padding: 2px 6px; font-size: 0.6rem; }
    .telemetry-value.show-coords .coords-hidden { display: inline; }
    .telemetry-value.show-coords .coords-toggle i { transform: rotate(90deg); }

    /* Map Last Updated */
    .map-last-updated {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 0.7rem;
      color: var(--text-muted);
      font-family: var(--font-mono);
      padding: 2px 8px;
      background: var(--bg-surface-alt);
      border-radius: 4px;
    }

    /* Preferences Grid */
    .prefs-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px;
      padding: 16px;
    }
    .pref-item {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .pref-label {
      font-size: 0.6rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      font-weight: 600;
    }
    .pref-value {
      font-size: 0.85rem;
      color: var(--text);
    }

    /* Coordinates toggle button */
    .coords-toggle {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 2px 8px;
      font-size: 0.6rem;
    }
  </style>
'''

# Add CSS to extra_css block
if '{% block extra_css %}' in content and css_injection not in content:
    content = content.replace('{% block extra_css %}', '{% block extra_css %}' + css_injection)
    print('✓ Added CSS')

# ============================================================
# 5. ADD JAVASCRIPT for status pill updates and coords toggle
# ============================================================
js_injection = '''
<script nonce="{{ csp_nonce }}">
  // Initialize status pill from existing subsystem indicators
  document.addEventListener('DOMContentLoaded', function() {
    const statusPill = document.getElementById('locationStatusPill');
    const statusDot = document.getElementById('locationStatusDot');
    const statusText = document.getElementById('locationStatusText');
    const publishStatus = document.getElementById('dcPublishStatus');
    const gpsStatus = document.getElementById('dcGpsStatus');
    const healthStatus = document.getElementById('dcHealthStatus');
    const authStatus = document.getElementById('dcAuthStatus');

    function updateStatusPill() {
      if (!statusPill) return;

      const isPublishing = publishStatus && !publishStatus.classList.contains('err') && publishStatus.textContent !== 'Idle';
      const gpsOk = gpsStatus && !gpsStatus.classList.contains('err');
      const healthOk = healthStatus && !healthStatus.classList.contains('err');
      const authOk = authStatus && !authStatus.classList.contains('err');
      const online = document.querySelector('[data-online-toggle]')?.checked === true;

      statusPill.classList.remove('status-pill--online', 'status-pill--publishing', 'status-pill--offline', 'status-pill--error');

      if (!online) {
        statusPill.classList.add('status-pill--offline');
        statusDot.style.background = 'var(--text-muted)';
        statusText.textContent = 'Offline';
      } else if (!authOk) {
        statusPill.classList.add('status-pill--error');
        statusDot.style.background = 'var(--red)';
        statusText.textContent = 'Auth required';
      } else if (!healthOk) {
        statusPill.classList.add('status-pill--error');
        statusDot.style.background = 'var(--red)';
        statusText.textContent = 'Degraded';
      } else if (isPublishing && gpsOk) {
        statusPill.classList.add('status-pill--publishing');
        statusDot.style.background = 'var(--blue)';
        statusText.textContent = 'Publishing';
      } else if (online && gpsOk) {
        statusPill.classList.add('status-pill--online');
        statusDot.style.background = 'var(--green)';
        statusText.textContent = 'Online';
      } else {
        statusPill.classList.add('status-pill--offline');
        statusDot.style.background = 'var(--text-muted)';
        statusText.textContent = 'Waiting for GPS…';
      }
    }

    // Watch for changes in subsystem indicators
    const observer = new MutationObserver(updateStatusPill);
    [publishStatus, gpsStatus, healthStatus, authStatus].forEach(el => {
      if (el) observer.observe(el, { attributes: true, childList: true, characterData: true, subtree: true });
    });

    // Initial update
    updateStatusPill();

    // Coordinates toggle
    document.querySelectorAll('.coords-toggle').forEach(btn => {
      btn.addEventListener('click', function() {
        const container = this.closest('.telemetry-value, .ws-v');
        if (container) {
          container.classList.toggle('show-coords');
          const hidden = container.querySelector('.coords-hidden');
          if (hidden) hidden.style.display = container.classList.contains('show-coords') ? 'inline' : 'none';
          this.querySelector('i').style.transform = container.classList.contains('show-coords') ? 'rotate(90deg)' : 'rotate(0deg)';
          this.innerHTML = container.classList.contains('show-coords')
            ? '<i class="fa-solid fa-map-pin"></i> Hide'
            : '<i class="fa-solid fa-map-pin"></i> Show';
        }
      });
    });
  });
</script>
'''

# Add JS before closing body or in extra_js block
if '{% block extra_js %}' in content:
    content = content.replace('{% block extra_js %}', '{% block extra_js %}' + js_injection)
    print('✓ Added JS')
else:
    # Try to add before </body>
    content = content.replace('</body>', js_injection + '\n</body>')
    print('✓ Added JS before </body>')

# Write the modified content
with open('templates/transport/driver/driver_dashboard.html', 'w') as f:
    f.write(content)

print('✓ All improvements applied')