/**
 * AFCON360 Heatmap & Demand Driver Dashboard
 * Interactive map with heatmap overlays, hot zones, and demand analytics
 * Version: 1.0.0
 */

(function () {
  "use strict";

  // ============================================================
  // CONFIGURATION & DATA
  // ============================================================

  // Hot zones data for Kampala area
  const HOT_ZONES = [
    {
      id: 'kololo',
      name: 'Kololo',
      lat: 0.3376,
      lng: 32.5895,
      demand: 'high',
      potentialEarnings: { min: 20000, max: 50000 },
      distanceKm: 3,
      color: '#EF4444'
    },
    {
      id: 'kampala_cbd',
      name: 'Kampala CBD',
      lat: 0.3136,
      lng: 32.5811,
      demand: 'high',
      potentialEarnings: { min: 20000, max: 45000 },
      distanceKm: 5,
      color: '#EF4444'
    },
    {
      id: 'ntinda',
      name: 'Ntinda',
      lat: 0.3606,
      lng: 32.6144,
      demand: 'high',
      potentialEarnings: { min: 15000, max: 40000 },
      distanceKm: 6,
      color: '#EF4444'
    },
    {
      id: 'makerere',
      name: 'Makerere University',
      lat: 0.3349,
      lng: 32.5684,
      demand: 'medium',
      potentialEarnings: { min: 12000, max: 30000 },
      distanceKm: 4,
      color: '#F97316'
    },
    {
      id: 'kisementi',
      name: 'Kisementi',
      lat: 0.3256,
      lng: 32.5921,
      demand: 'medium',
      potentialEarnings: { min: 10000, max: 28000 },
      distanceKm: 3,
      color: '#F97316'
    },
    {
      id: 'kyambogo',
      name: 'Kyambogo University',
      lat: 0.3514,
      lng: 32.6289,
      demand: 'medium',
      potentialEarnings: { min: 11000, max: 29000 },
      distanceKm: 7,
      color: '#F97316'
    },
    {
      id: 'bugolobi',
      name: 'Bugolobi',
      lat: 0.3036,
      lng: 32.6156,
      demand: 'medium',
      potentialEarnings: { min: 10000, max: 27000 },
      distanceKm: 6,
      color: '#F97316'
    }
  ];

  // Recent trips sample data
  const RECENT_TRIPS = [
    {
      id: 1,
      route: 'Kampala CBD → Ntinda',
      time: '10:24 AM',
      duration: '22 min',
      fare: 18000,
      status: 'completed'
    },
    {
      id: 2,
      route: 'Kololo → Muyenga',
      time: '09:41 AM',
      duration: '18 min',
      fare: 15000,
      status: 'completed'
    },
    {
      id: 3,
      route: 'Nakasero → Bugolobi',
      time: '08:12 AM',
      duration: '25 min',
      fare: 12500,
      status: 'completed'
    },
    {
      id: 4,
      route: 'Makerere → Wandegeya',
      time: '07:30 AM',
      duration: '15 min',
      fare: 8500,
      status: 'completed'
    },
    {
      id: 5,
      route: 'Kisementi → Nakawa',
      time: '06:45 AM',
      duration: '20 min',
      fare: 11000,
      status: 'completed'
    }
  ];

  // Weekly earnings data (UGX)
  const WEEKLY_EARNINGS = {
    labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
    data: [125000, 142000, 138000, 155000, 180000, 210000, 95000]
  };

  // ============================================================
  // STATE MANAGEMENT
  // ============================================================

  let map = null;
  let heatmapLayer = null;
  let hotspotMarkers = [];
  let driverMarker = null;
  let earningsChart = null;
  let currentDemandFilter = 'all';
  let currentTrafficFilter = 'off';

  const root = document.getElementById('heatmapDashboard');
  if (!root) return;

  // Get driver data from DOM
  const driverData = {
    id: root.getAttribute('data-driver-id'),
    name: root.getAttribute('data-driver-name'),
    code: root.getAttribute('data-driver-code'),
    lat: parseFloat(root.getAttribute('data-driver-lat')),
    lng: parseFloat(root.getAttribute('data-driver-lng')),
    isOnline: root.getAttribute('data-is-online') === '1',
    tripsToday: parseInt(root.getAttribute('data-trips-today') || '12', 10),
    earningsToday: parseInt(root.getAttribute('data-earnings-today') || '145000', 10),
    acceptanceRate: parseInt(root.getAttribute('data-acceptance-rate') || '98', 10),
    rating: parseFloat(root.getAttribute('data-rating') || '4.8')
  };

  // ============================================================
  // UTILITY FUNCTIONS
  // ============================================================

  function formatCurrency(amount) {
    return 'UGX ' + amount.toLocaleString();
  }

  function formatDistance(km) {
    return km + ' km';
  }

  function getDemandLabel(demand) {
    const labels = { high: 'High Demand', medium: 'Medium Demand', low: 'Low Demand' };
    return labels[demand] || demand;
  }

  function getDemandClass(demand) {
    return demand === 'high' ? 'high' : demand === 'medium' ? 'medium' : 'low';
  }

  // ============================================================
  // MAP INITIALIZATION
  // ============================================================

  function initMap() {
    const mapContainer = document.getElementById('heatmapMap');
    if (!mapContainer) return;

    // Initialize Leaflet map centered on Kampala
    map = L.map('heatmapMap', {
      center: [0.3476, 32.5825],
      zoom: 13,
      zoomControl: false,
      attributionControl: true
    });

    // Add tile layer (OpenStreetMap)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors',
      maxZoom: 19
    }).addTo(map);

    // Add driver marker
    addDriverMarker();

    // Add hotspot markers
    addHotspotMarkers();

    // Add heatmap layer
    addHeatmapLayer();

    // Fit map to show all hotspots
    fitMapToHotspots();

    // Set up map event listeners
    setupMapEvents();
  }

  function addDriverMarker() {
    const driverIcon = L.divIcon({
      className: 'driver-marker',
      html: `
        <div class="driver-pulse"></div>
        <div class="driver-dot" style="background: #2563eb;"></div>
      `,
      iconSize: [48, 48],
      iconAnchor: [24, 24]
    });

    driverMarker = L.marker([driverData.lat, driverData.lng], {
      icon: driverIcon,
      zIndexOffset: 1000
    }).addTo(map);

    driverMarker.bindPopup(`
      <div style="text-align: center; padding: 4px;">
        <strong>You are here</strong><br>
        <small>${driverData.name}</small><br>
        <small>${driverData.code}</small>
      </div>
    `);
  }

  function addHotspotMarkers() {
    HOT_ZONES.forEach((zone, index) => {
      const marker = L.marker([zone.lat, zone.lng], {
        icon: createHotspotIcon(zone, index + 1),
        zIndexOffset: 500
      }).addTo(map);

      // Create popup content
      const popupContent = `
        <div style="min-width: 180px; padding: 4px;">
          <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
            <div style="width: 24px; height: 24px; border-radius: 50%; background: linear-gradient(135deg, ${zone.color}, ${adjustColor(zone.color, -20)}); display: flex; align-items: center; justify-content: center; color: #fff; font-weight: 700; font-size: 0.7rem;">${index + 1}</div>
            <strong style="font-size: 0.9rem;">${zone.name}</strong>
          </div>
          <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 6px;">
            <span class="hot-zone-demand ${getDemandClass(zone.demand)}" style="font-size: 0.65rem; padding: 2px 8px;">${getDemandLabel(zone.demand)}</span>
          </div>
          <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 6px; color: var(--green); font-weight: 700; font-family: var(--font-display);">
            <i class="fa-solid fa-money-bill-wave" style="font-size: 0.75rem;"></i>
            <span>Potential: ${formatCurrency(zone.potentialEarnings.min)}–${formatCurrency(zone.potentialEarnings.max)}/hr</span>
          </div>
          <div style="display: flex; align-items: center; gap: 6px; color: var(--text-muted); font-size: 0.75rem;">
            <i class="fa-solid fa-location-dot"></i>
            <span>${zone.distanceKm} km from you</span>
          </div>
        </div>
      `;

      marker.bindPopup(popupContent);

      hotspotMarkers.push({ marker, zone });
    });
  }

  function createHotspotIcon(zone, rank) {
    const size = zone.demand === 'high' ? 60 : 50;
    return L.divIcon({
      className: 'hotspot-marker',
      html: `
        <div class="hotspot-pulse" style="background: ${zone.color}33; width: ${size}px; height: ${size}px;"></div>
        <div class="hotspot-core" style="background: ${zone.color}; width: ${zone.demand === 'high' ? 14 : 12}px; height: ${zone.demand === 'high' ? 14 : 12}px; margin: -${zone.demand === 'high' ? 7 : 6}px 0 0 -${zone.demand === 'high' ? 7 : 6}px;"></div>
        <div class="hotspot-label" style="background: ${zone.color}; font-size: ${zone.demand === 'high' ? '0.7rem' : '0.65rem'};">${zone.name}</div>
      `,
      iconSize: [size, size + 20],
      iconAnchor: [size / 2, size / 2 + 10]
    });
  }

  function addHeatmapLayer() {
    // Create heatmap data points with intensity based on demand
    const heatData = HOT_ZONES.map(zone => {
      const intensity = zone.demand === 'high' ? 1.0 : zone.demand === 'medium' ? 0.6 : 0.3;
      return [zone.lat, zone.lng, intensity];
    });

    // Add a simple circle-based heatmap visualization using Leaflet circles
    heatData.forEach((point, index) => {
      const zone = HOT_ZONES[index];
      const radius = zone.demand === 'high' ? 800 : zone.demand === 'medium' ? 600 : 400;
      const opacity = zone.demand === 'high' ? 0.35 : zone.demand === 'medium' ? 0.25 : 0.15;

      L.circle([point[0], point[1]], {
        radius: radius,
        color: zone.color,
        fillColor: zone.color,
        fillOpacity: opacity,
        weight: 0,
        className: 'heatmap-circle'
      }).addTo(map);
    });
  }

  function fitMapToHotspots() {
    if (hotspotMarkers.length === 0) return;

    const bounds = L.latLngBounds(
      hotspotMarkers.map(h => h.marker.getLatLng())
    );
    // Add driver location to bounds
    bounds.extend([driverData.lat, driverData.lng]);

    map.fitBounds(bounds, {
      padding: [50, 50],
      maxZoom: 14
    });
  }

  function setupMapEvents() {
    // Zoom controls
    document.getElementById('zoomIn')?.addEventListener('click', () => map.zoomIn());
    document.getElementById('zoomOut')?.addEventListener('click', () => map.zoomOut());
    document.getElementById('recenterMap')?.addEventListener('click', recenterMap);

    // Search input
    document.getElementById('mapSearch')?.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') {
        searchLocation(e.target.value);
      }
    });

    // Demand filter
    document.getElementById('demandToggle')?.addEventListener('change', (e) => {
      currentDemandFilter = e.target.value;
      filterHotspots();
    });

    // Traffic filter
    document.getElementById('trafficToggle')?.addEventListener('change', (e) => {
      currentTrafficFilter = e.target.value;
      // Traffic layer would be implemented here
      console.log('Traffic filter:', currentTrafficFilter);
    });
  }

  function recenterMap() {
    map.setView([driverData.lat, driverData.lng], 14, { animate: true });
  }

  function searchLocation(query) {
    if (!query.trim()) return;

    // Use Nominatim for geocoding (free, no API key needed for demo)
    fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query + ', Kampala, Uganda')}&limit=5`)
      .then(res => res.json())
      .then(results => {
        if (results.length > 0) {
          const result = results[0];
          map.setView([result.lat, result.lon], 15, { animate: true });
          
          // Add temporary marker
          const tempMarker = L.marker([result.lat, result.lon], {
            icon: L.divIcon({
              className: 'search-result-marker',
              html: '<i class="fa-solid fa-map-pin" style="font-size: 2rem; color: #2563eb; text-shadow: 0 2px 4px rgba(0,0,0,0.3);"></i>',
              iconSize: [32, 32],
              iconAnchor: [16, 32]
            })
          }).addTo(map);

          tempMarker.bindPopup(`<strong>${result.display_name}</strong>`).openPopup();

          // Remove after 30 seconds
          setTimeout(() => map.removeLayer(tempMarker), 30000);
        }
      })
      .catch(err => console.warn('Geocoding failed:', err));
  }

  function filterHotspots() {
    hotspotMarkers.forEach(({ marker, zone }) => {
      const show = currentDemandFilter === 'all' || zone.demand === currentDemandFilter;
      if (show) {
        marker.addTo(map);
      } else {
        map.removeLayer(marker);
      }
    });
  }

  function adjustColor(color, amount) {
    const hex = color.replace('#', '');
    const num = parseInt(hex, 16);
    const r = Math.max(0, Math.min(255, (num >> 16) + amount));
    const g = Math.max(0, Math.min(255, ((num >> 8) & 0x00FF) + amount));
    const b = Math.max(0, Math.min(255, (num & 0x0000FF) + amount));
    return '#' + ((r << 16) | (g << 8) | b).toString(16).padStart(6, '0');
  }

  // ============================================================
  // UI RENDERING
  // ============================================================

  function renderDriverInfo() {
    document.getElementById('driverNameDisplay').textContent = driverData.name;
    document.getElementById('driverCodeDisplay').textContent = driverData.code;
    
    const statusDot = document.getElementById('statusDot');
    const statusText = document.getElementById('statusText');
    const statusToggle = document.getElementById('statusToggle');

    if (driverData.isOnline) {
      statusDot.classList.add('online');
      statusText.textContent = 'ONLINE';
      statusToggle.style.background = 'var(--green-dim)';
      statusToggle.style.color = 'var(--green)';
    } else {
      statusDot.classList.remove('online');
      statusText.textContent = 'OFFLINE';
      statusToggle.style.background = 'var(--gray-dim)';
      statusToggle.style.color = 'var(--gray)';
    }
  }

  function renderKPIs() {
    document.getElementById('tripsToday').textContent = driverData.tripsToday;
    document.getElementById('earningsToday').textContent = formatCurrency(driverData.earningsToday);
    document.getElementById('ratingToday').textContent = driverData.rating.toFixed(1);

    document.getElementById('kpiTrips').textContent = driverData.tripsToday;
    document.getElementById('kpiEarnings').textContent = formatCurrency(driverData.earningsToday);
    document.getElementById('kpiAcceptance').textContent = driverData.acceptanceRate + '%';
    document.getElementById('kpiRating').textContent = driverData.rating.toFixed(1);
  }

  function renderHotZones() {
    const container = document.getElementById('hotZonesList');
    if (!container) return;

    container.innerHTML = HOT_ZONES.map((zone, index) => `
      <div class="hot-zone-item" data-zone="${zone.id}" style="cursor: pointer;" onclick="window.heatmapDashboard.focusZone('${zone.id}')">
        <div class="hot-zone-rank">${index + 1}</div>
        <div class="hot-zone-info">
          <div class="hot-zone-name">${zone.name}</div>
          <div class="hot-zone-meta">
            <span class="hot-zone-demand ${getDemandClass(zone.demand)}">${getDemandLabel(zone.demand)}</span>
            <span class="hot-zone-earnings">${formatCurrency(zone.potentialEarnings.min)}–${formatCurrency(zone.potentialEarnings.max)}/hr</span>
            <span class="hot-zone-distance"><i class="fa-solid fa-location-dot"></i> ${formatDistance(zone.distanceKm)}</span>
          </div>
        </div>
      </div>
    `).join('');
  }

  function renderRecentTrips() {
    const container = document.getElementById('recentTripsList');
    if (!container) return;

    container.innerHTML = RECENT_TRIPS.map(trip => `
      <div class="trip-item">
        <div class="trip-time">
          <div class="trip-time-main">${trip.time}</div>
          <div class="trip-duration">${trip.duration}</div>
        </div>
        <div class="trip-details">
          <div class="trip-route">${trip.route}</div>
          <div class="trip-meta">
            <span><i class="fa-solid fa-road"></i> ${trip.duration}</span>
            <span><i class="fa-solid fa-circle-check" style="color: var(--green);"></i> Completed</span>
          </div>
        </div>
        <div class="trip-fare">${formatCurrency(trip.fare)}</div>
        <button type="button" class="btn btn-ghost btn-sm trip-action"><i class="fa-solid fa-eye"></i> Details</button>
      </div>
    `).join('');
  }

  function renderGoals() {
    const tripsProgress = Math.min(100, (driverData.tripsToday / 20) * 100);
    const earningsProgress = Math.min(100, (driverData.earningsToday / 300000) * 100);

    document.getElementById('tripsProgress').style.width = tripsProgress + '%';
    document.getElementById('tripsProgressText').textContent = `${driverData.tripsToday}/20`;
    document.getElementById('earningsProgress').style.width = earningsProgress + '%';
    document.getElementById('earningsProgressText').textContent = `${formatCurrency(driverData.earningsToday)}/${formatCurrency(300000)}`;
  }

  function initEarningsChart() {
    const ctx = document.getElementById('earningsChart');
    if (!ctx) return;

    earningsChart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: WEEKLY_EARNINGS.labels,
        datasets: [{
          label: 'Earnings (UGX)',
          data: WEEKLY_EARNINGS.data,
          backgroundColor: 'rgba(16, 185, 129, 0.8)',
          borderColor: '#10B981',
          borderWidth: 0,
          borderRadius: 6,
          borderSkipped: false,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: 'var(--bg-surface)',
            titleColor: 'var(--text-primary)',
            bodyColor: 'var(--text-secondary)',
            borderColor: 'var(--border-light)',
            borderWidth: 1,
            padding: 12,
            callbacks: {
              label: (context) => 'Earnings: ' + formatCurrency(context.raw)
            }
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: {
              color: 'var(--text-muted)',
              font: { family: 'var(--font-sans)', size: 11 }
            }
          },
          y: {
            grid: {
              color: 'var(--border-light)',
              drawBorder: false
            },
            ticks: {
              color: 'var(--text-muted)',
              font: { family: 'var(--font-mono)', size: 10 },
              callback: (value) => formatCurrency(value)
            },
            beginAtZero: true
          }
        },
        interaction: {
          intersect: false,
          mode: 'index'
        }
      }
    });
  }

  function updateGPSStatus() {
    const statusDot = document.getElementById('gpsStatusDot');
    const statusText = document.getElementById('gpsStatusText');
    
    if (statusDot && statusText) {
      statusDot.style.background = 'var(--green)';
      statusDot.style.boxShadow = '0 0 6px var(--green)';
      statusText.textContent = "You're visible to riders — Good GPS signal • Updated just now";
    }
  }

  // ============================================================
  // STATUS TOGGLE
  // ============================================================

  function setupStatusToggle() {
    const toggle = document.getElementById('statusToggle');
    if (!toggle) return;

    toggle.addEventListener('click', async () => {
      const newStatus = !driverData.isOnline;
      
      try {
        // Show loading state
        toggle.style.opacity = '0.7';
        toggle.style.pointerEvents = 'none';

        const response = await fetch(`/api/transport/drivers/${driverData.id}/go-live`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': root.getAttribute('data-csrf')
          },
          body: JSON.stringify({ is_online: newStatus })
        });

        const result = await response.json();
        
        if (result.success) {
          driverData.isOnline = newStatus;
          renderDriverInfo();
          
          // Show success feedback
          showToast(newStatus ? 'You are now online' : 'You are now offline', 'success');
        } else {
          showToast(result.message || 'Failed to update status', 'error');
        }
      } catch (error) {
        console.error('Status toggle error:', error);
        showToast('Network error. Please try again.', 'error');
      } finally {
        toggle.style.opacity = '1';
        toggle.style.pointerEvents = 'auto';
      }
    });
  }

  function showToast(message, type = 'info') {
    // Simple toast implementation
    const toast = document.createElement('div');
    toast.className = `alert alert-${type === 'error' ? 'red' : type === 'success' ? 'green' : 'blue'}`;
    toast.style.cssText = 'position: fixed; top: 80px; right: 24px; z-index: 1000; min-width: 280px; box-shadow: var(--shadow-lg); animation: slideIn 0.3s ease;';
    toast.innerHTML = `
      <i class="fa-solid fa-${type === 'error' ? 'circle-exclamation' : type === 'success' ? 'circle-check' : 'circle-info'}"></i>
      <span style="flex:1;">${message}</span>
      <button class="alert-close" onclick="this.parentElement.remove()"><i class="fa-solid fa-xmark"></i></button>
    `;
    document.body.appendChild(toast);
    
    setTimeout(() => {
      toast.style.animation = 'slideOut 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  // ============================================================
  // PUBLIC API
  // ============================================================

  window.heatmapDashboard = {
    focusZone: function(zoneId) {
      const zone = HOT_ZONES.find(z => z.id === zoneId);
      if (zone && map) {
        map.setView([zone.lat, zone.lng], 15, { animate: true });
        // Find and open the marker popup
        const markerData = hotspotMarkers.find(m => m.zone.id === zoneId);
        if (markerData) {
          markerData.marker.openPopup();
        }
      }
    },
    
    refreshData: function() {
      // Would fetch fresh data from API
      console.log('Refreshing heatmap data...');
    },
    
    getMap: function() {
      return map;
    }
  };

  // ============================================================
  // INITIALIZATION
  // ============================================================

  function init() {
    // Render static UI
    renderDriverInfo();
    renderKPIs();
    renderHotZones();
    renderRecentTrips();
    renderGoals();
    updateGPSStatus();

    // Initialize map
    initMap();

    // Initialize chart
    initEarningsChart();

    // Setup event listeners
    setupStatusToggle();

    // Handle period selector for earnings chart
    document.getElementById('earningsPeriod')?.addEventListener('change', (e) => {
      if (earningsChart) {
        // In a real app, this would fetch data for the selected period
        console.log('Period changed to:', e.target.value);
      }
    });

    console.log('[HeatmapDashboard] Initialized');
  }

  // Wait for DOM and Leaflet to be ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Add toast animations
  const style = document.createElement('style');
  style.textContent = `
    @keyframes slideIn {
      from { transform: translateX(100%); opacity: 0; }
      to { transform: translateX(0); opacity: 1; }
    }
    @keyframes slideOut {
      from { transform: translateX(0); opacity: 1; }
      to { transform: translateX(100%); opacity: 0; }
    }
  `;
  document.head.appendChild(style);

})();