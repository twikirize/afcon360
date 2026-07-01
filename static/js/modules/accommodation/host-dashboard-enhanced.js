/**
 * AFCON 360 - Enhanced Host Dashboard
 * World-class UI/UX with real-time updates and analytics
 */

class HostDashboard {
    constructor() {
        this.ws = null;
        this.stats = {};
        this.charts = {};
        this.init();
    }

    init() {
        this.initWebSocket();
        this.initCharts();
        this.initEventListeners();
        this.initKeyboardShortcuts();
        this.initNotifications();
        console.log('🚀 HostDashboard initialized');
    }

    // ── WebSocket Connection ────────────────────────────────────────
    initWebSocket() {
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProtocol}//${window.location.host}/ws/host-dashboard`;
        
        try {
            this.ws = new WebSocket(wsUrl);
            
            this.ws.onopen = () => {
                console.log('🔌 WebSocket connected');
                this.send('subscribe', { channel: 'host_updates' });
            };
            
            this.ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.handleWebSocketMessage(data);
            };
            
            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
            };
            
            this.ws.onclose = () => {
                console.log('🔌 WebSocket disconnected, reconnecting...');
                setTimeout(() => this.initWebSocket(), 3000);
            };
        } catch (error) {
            console.warn('WebSocket not available, using polling fallback');
            this.initPolling();
        }
    }

    initPolling() {
        setInterval(() => {
            this.fetchUpdates();
        }, 30000);
    }

    send(action, data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ action, data }));
        }
    }

    handleWebSocketMessage(data) {
        switch (data.type) {
            case 'stats_update':
                this.updateStats(data.payload);
                break;
            case 'new_booking':
                this.showNotification('New Booking!', data.payload);
                break;
            case 'new_review':
                this.showNotification('New Review', data.payload);
                break;
            default:
                console.log('Unknown message type:', data.type);
        }
    }

    async fetchUpdates() {
        try {
            const response = await fetch('/accommodation/host/dashboard/data');
            const data = await response.json();
            this.updateStats(data);
        } catch (error) {
            console.error('Failed to fetch updates:', error);
        }
    }

    // ── Chart Initialization ────────────────────────────────────────
    initCharts() {
        const initialData = window.initialDashboardData || { monthly_revenue: [], occupancy_rate: 0 };

        // Revenue Chart
        const revenueCtx = document.getElementById('revenueChart');
        if (revenueCtx) {
            const revData = [...initialData.monthly_revenue].reverse();
            const labels = revData.map(r => r.month);
            const values = revData.map(r => r.amount);

            this.charts.revenue = new Chart(revenueCtx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Revenue',
                        data: values,
                        borderColor: '#FF385C',
                        backgroundColor: 'rgba(255, 56, 92, 0.1)',
                        fill: true,
                        tension: 0.4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                callback: value => '$' + value.toLocaleString()
                            }
                        }
                    }
                }
            });
        }

        // Occupancy Chart
        const occupancyCtx = document.getElementById('occupancyChart');
        if (occupancyCtx) {
            const occupied = initialData.occupancy_rate || 0;
            const available = Math.max(0, 100 - occupied);
            this.charts.occupancy = new Chart(occupancyCtx, {
                type: 'doughnut',
                data: {
                    labels: ['Available', 'Booked'],
                    datasets: [{
                        data: [available, occupied],
                        backgroundColor: ['#E8EAED', '#FF385C'],
                        borderWidth: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: 'bottom' }
                    }
                }
            });
        }
    }

    updateStats(data) {
        // Update UI with new data
        document.querySelectorAll('.stat-value-modern').forEach(el => {
            const key = el.dataset.stat;
            if (data[key] !== undefined) {
                const endVal = parseFloat(data[key]);
                // strip out $ or other characters for starting value
                const startVal = parseFloat(el.textContent.replace(/[^0-9.-]+/g,"")) || 0;
                
                // Format the counter animation properly if it's currency
                const isCurrency = el.textContent.includes('$');
                this.animateValue(el, startVal, endVal, isCurrency);
            }
        });

        // Update charts with new data if available
        if (data.monthly_revenue && this.charts.revenue) {
            const revData = [...data.monthly_revenue].reverse();
            this.charts.revenue.data.labels = revData.map(r => r.month);
            this.charts.revenue.data.datasets[0].data = revData.map(r => r.amount);
            this.charts.revenue.update();
        }

        if (data.occupancy_rate !== undefined && this.charts.occupancy) {
            const occupied = data.occupancy_rate;
            const available = Math.max(0, 100 - occupied);
            this.charts.occupancy.data.datasets[0].data = [available, occupied];
            this.charts.occupancy.update();
        }
    }

    animateValue(element, start, end, isCurrency = false) {
        const duration = 1000;
        const startTime = performance.now();
        
        const update = (currentTime) => {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            const easeOut = 1 - Math.pow(1 - progress, 3);
            const current = Math.round(start + (end - start) * easeOut);
            
            element.textContent = (isCurrency ? '$' : '') + current.toLocaleString();
            
            if (progress < 1) {
                requestAnimationFrame(update);
            }
        };
        
        requestAnimationFrame(update);
    }

    // ── Event Listeners ─────────────────────────────────────────────
    initEventListeners() {
        // Quick Action buttons
        document.querySelectorAll('.quick-action-modern').forEach(btn => {
            btn.addEventListener('click', (e) => {
                this.trackEvent('quick_action', {
                    action: btn.querySelector('.action-label')?.textContent || 'unknown'
                });
            });
        });

        // Booking items
        document.querySelectorAll('.booking-item-modern').forEach(item => {
            item.addEventListener('click', () => {
                const bookingId = item.dataset.bookingId;
                if (bookingId) {
                    window.location.href = `/accommodation/host/bookings/${bookingId}`;
                }
            });
        });

        // Listing cards
        document.querySelectorAll('.listing-card-modern').forEach(card => {
            card.addEventListener('mouseenter', () => {
                // Track interest
                const listingId = card.dataset.listingId;
                if (listingId) {
                    this.trackEvent('listing_hover', { listingId });
                }
            });
        });
    }

    // ── Keyboard Shortcuts ──────────────────────────────────────────
    initKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // ⌘N or Ctrl+N = New Listing
            if ((e.metaKey || e.ctrlKey) && e.key === 'n') {
                e.preventDefault();
                window.location.href = '/accommodation/host/listings/create';
            }
            // ⌘B or Ctrl+B = Bookings
            if ((e.metaKey || e.ctrlKey) && e.key === 'b') {
                e.preventDefault();
                window.location.href = '/accommodation/host/bookings';
            }
            // ⌘C or Ctrl+C = Calendar
            if ((e.metaKey || e.ctrlKey) && e.key === 'c') {
                e.preventDefault();
                window.location.href = '/accommodation/host/calendar';
            }
            // ⌘E or Ctrl+E = Earnings
            if ((e.metaKey || e.ctrlKey) && e.key === 'e') {
                e.preventDefault();
                window.location.href = '/accommodation/host/earnings';
            }
            // ? = Show shortcuts
            if (e.key === '?' && !e.ctrlKey && !e.metaKey) {
                e.preventDefault();
                this.showShortcuts();
            }
        });
    }

    showShortcuts() {
        const shortcuts = `
            Keyboard Shortcuts:
            Ctrl+N  → New Listing
            Ctrl+B  → Bookings
            Ctrl+C  → Calendar
            Ctrl+E  → Earnings
            ?       → Show this help
        `;
        alert(shortcuts);
    }

    // ── Notifications ───────────────────────────────────────────────
    initNotifications() {
        // Request notification permission
        if ('Notification' in window && Notification.permission === 'default') {
            Notification.requestPermission();
        }
    }

    showNotification(title, body) {
        // Browser notification
        if ('Notification' in window && Notification.permission === 'granted') {
            new Notification(title, {
                body: typeof body === 'string' ? body : JSON.stringify(body),
                icon: '/static/images/notification-icon.png'
            });
        }
        
        // In-app notification
        const container = document.getElementById('notification-container');
        if (container) {
            const notification = document.createElement('div');
            notification.className = 'notification-toast';
            notification.innerHTML = `
                <div class="notification-content">
                    <strong>${title}</strong>
                    <p>${typeof body === 'string' ? body : body.message || ''}</p>
                </div>
                <button onclick="this.parentElement.remove()">×</button>
            `;
            container.appendChild(notification);
            setTimeout(() => notification.remove(), 5000);
        }
    }

    // ── Analytics Tracking ──────────────────────────────────────────
    trackEvent(event, properties = {}) {
        // Send to analytics
        fetch('/accommodation/host/api/track', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                event,
                properties,
                timestamp: new Date().toISOString()
            })
        }).catch(error => console.warn('Analytics error:', error));
    }
}

// ── Initialize ─────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new HostDashboard();
});
