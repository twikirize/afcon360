/* Phase 3 – Intelligence UI Module */
(function(){
  'use strict';

  const Dashboard = {
    // DOM caches
    els: {},

    init() {
      this.cacheElements();
      this.bindEvents();
      this.refreshAllData();
      // Auto-refresh every 30 seconds
      setInterval(() => this.refreshAllData(), 30000);
    },

    cacheElements() {
      this.els = {
        performanceBody: document.getElementById('performanceBody'),
        queueBody:       document.getElementById('queueBody'),
        alertContainer:  document.getElementById('alertContainer'),
        auditChart:      document.getElementById('auditChart'),
        // SLA indicators will be applied to existing rows
        submissionRows:  document.querySelectorAll('#pendingSubmissionsTable tbody tr'),
      };
    },

    bindEvents() {
      // No additional events needed for now
    },

    // ──────────────────────────────────────────────────────────────
    // FETCH HELPERS
    // ──────────────────────────────────────────────────────────────

    async fetchJSON(url) {
      const res = await fetch(url, {
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    },

    async refreshAllData() {
      try {
        const [perf, queue, audit] = await Promise.all([
          this.fetchJSON('/admin/moderator/performance'),
          this.fetchJSON('/admin/moderator/queue_metrics'),
          this.fetchJSON('/admin/moderator/audit_insights'),
        ]);
        this.renderPerformance(perf);
        this.renderQueue(queue);
        this.renderAuditChart(audit);
        this.renderAlerts(perf, queue);
        this.applySLAIndicators();
      } catch (e) {
        console.warn('Dashboard refresh failed:', e);
      }
    },

    // ──────────────────────────────────────────────────────────────
    // PERFORMANCE PANEL
    // ──────────────────────────────────────────────────────────────

    renderPerformance(data) {
      const container = this.els.performanceBody;
      if (!container) return;

      if (!data || data.length === 0) {
        container.innerHTML = `<div class="empty"><i class="fas fa-chart-bar"></i><p>No performance data yet</p></div>`;
        return;
      }

      // Sort by processed descending
      data.sort((a, b) => b.processed - a.processed);

      // Find fastest (lowest avg time) and slowest (highest avg time) among those with >0 processed
      const withTime = data.filter(d => d.processed > 0);
      let fastest = null, slowest = null;
      if (withTime.length > 0) {
        fastest = withTime.reduce((a, b) => (a.avg_processing_time < b.avg_processing_time ? a : b));
        slowest = withTime.reduce((a, b) => (a.avg_processing_time > b.avg_processing_time ? a : b));
      }

      let html = `<table class="tbl"><thead><tr><th>Username</th><th>Processed</th><th>Avg Time (s)</th></tr></thead><tbody>`;
      data.forEach(d => {
        let rowClass = '';
        if (fastest && d.user_id === fastest.user_id) rowClass = ' style="background:rgba(74,222,128,.08);"';
        else if (slowest && d.user_id === slowest.user_id) rowClass = ' style="background:rgba(224,82,82,.08);"';
        html += `<tr${rowClass}><td>${d.username}</td><td>${d.processed}</td><td>${d.avg_processing_time.toFixed(2)}</td></tr>`;
      });
      html += `</tbody></table>`;
      container.innerHTML = html;
    },

    // ──────────────────────────────────────────────────────────────
    // QUEUE ANALYTICS PANEL
    // ──────────────────────────────────────────────────────────────

    renderQueue(data) {
      const container = this.els.queueBody;
      if (!container) return;

      if (!data) {
        container.innerHTML = `<div class="empty"><i class="fas fa-clock"></i><p>No queue data</p></div>`;
        return;
      }

      const totalPending = data.total_pending || 0;
      const unassigned   = data.unassigned_count || 0;
      const oldestSec    = data.oldest_item_age_sec || 0;
      const oldestMin    = Math.round(oldestSec / 60);

      // Visual warnings
      const oldestClass = oldestSec > 3600 ? 'b-critical' : (oldestSec > 600 ? 'b-high' : 'b-normal');
      const unassignedClass = unassigned > 10 ? 'b-high' : 'b-normal';

      let html = `<table class="tbl"><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>`;
      html += `<tr><td>Total Pending</td><td><span class="badge b-normal">${totalPending}</span></td></tr>`;
      html += `<tr><td>Unassigned</td><td><span class="badge ${unassignedClass}">${unassigned}</span></td></tr>`;
      html += `<tr><td>Oldest Item Age</td><td><span class="badge ${oldestClass}">${oldestMin} min</span></td></tr>`;
      html += `</tbody></table>`;
      container.innerHTML = html;
    },

    // ──────────────────────────────────────────────────────────────
    // MINI CHART (AUDIT INSIGHTS)
    // ──────────────────────────────────────────────────────────────

    renderAuditChart(data) {
      const container = this.els.auditChart;
      if (!container) return;

      if (!data || data.length === 0) {
        container.innerHTML = `<div class="empty"><i class="fas fa-chart-bar"></i><p>No audit data</p></div>`;
        return;
      }

      const maxActions = Math.max(...data.map(d => d.actions), 1);
      let html = `<div style="display:flex;gap:8px;align-items:flex-end;height:120px;padding:8px 0;">`;
      data.forEach(d => {
        const heightPct = (d.actions / maxActions) * 100;
        html += `<div style="flex:1;display:flex;flex-direction:column;align-items:center;">`;
        html += `<div style="width:100%;background:var(--gold);border-radius:4px 4px 0 0;height:${heightPct}%;min-height:4px;transition:height .3s;"></div>`;
        html += `<span style="font-size:9px;color:var(--muted);margin-top:4px;">${d.moderator_id}</span>`;
        html += `</div>`;
      });
      html += `</div>`;
      container.innerHTML = html;
    },

    // ──────────────────────────────────────────────────────────────
    // LIVE ALERTS
    // ──────────────────────────────────────────────────────────────

    renderAlerts(perf, queue) {
      const container = this.els.alertContainer;
      if (!container) return;

      const alerts = [];

      // Critical flags from performance? Not directly available. We'll use queue metrics.
      // We'll check if oldest > 1 hour or unassigned > 10
      if (queue) {
        if (queue.oldest_item_age_sec > 3600) {
          alerts.push({ type: 'critical', message: `Oldest queue item > 1 hour (${Math.round(queue.oldest_item_age_sec/60)} min)` });
        }
        if (queue.unassigned_count > 10) {
          alerts.push({ type: 'warning', message: `Unassigned items: ${queue.unassigned_count} (threshold > 10)` });
        }
      }

      // Clear existing alerts
      container.innerHTML = '';

      alerts.forEach((alert, idx) => {
        const el = document.createElement('div');
        el.className = `alert alert-${alert.type}`;
        el.textContent = alert.message;
        el.style.cssText = `
          background: ${alert.type === 'critical' ? 'rgba(224,82,82,.15)' : 'rgba(251,191,36,.15)'};
          border: 1px solid ${alert.type === 'critical' ? 'rgba(224,82,82,.3)' : 'rgba(251,191,36,.3)'};
          color: ${alert.type === 'critical' ? 'var(--red)' : 'var(--amber)'};
          padding: 8px 12px;
          border-radius: 6px;
          margin-bottom: 6px;
          font-size: 12px;
          animation: slideIn .3s ease;
        `;
        container.appendChild(el);

        // Auto-dismiss after 5s
        setTimeout(() => {
          el.style.transition = 'opacity .3s';
          el.style.opacity = '0';
          setTimeout(() => el.remove(), 300);
        }, 5000);
      });
    },

    // ──────────────────────────────────────────────────────────────
    // SLA INDICATORS
    // ──────────────────────────────────────────────────────────────

    applySLAIndicators() {
      const rows = this.els.submissionRows;
      if (!rows || rows.length === 0) return;

      const now = new Date();
      rows.forEach(row => {
        const dateCell = row.querySelector('td.mono');
        if (!dateCell) return;
        const dateStr = dateCell.textContent.trim();
        // Expected format: "Apr 28" (month day)
        const created = new Date(dateStr + ' ' + now.getFullYear());
        if (isNaN(created.getTime())) return;
        const ageHours = (now - created) / (1000 * 60 * 60);
        const statusCell = row.querySelector('td:last-child');
        if (!statusCell) return;
        if (ageHours > 6) {
          statusCell.classList.add('b-critical');
        } else if (ageHours > 2) {
          statusCell.classList.add('b-high');
        }
      });
    },
  };

  // Initialize on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => Dashboard.init());
  } else {
    Dashboard.init();
  }
})();
