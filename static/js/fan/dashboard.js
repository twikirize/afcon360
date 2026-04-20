/**
 * AFCON360 Fan Dashboard - Outlook 3-Pane Layout
 * Handles pane switching, item selection, and responsive behavior
 */

class FanDashboard {
    constructor() {
        this.currentPane = 'dashboard';
        this.selectedItem = null;
        this.isMobile = window.innerWidth <= 768;

        this.init();
    }

    init() {
        this.bindEvents();
        this.setupMobileNav();
        this.loadDefaultContent();
    }

    bindEvents() {
        // Navigation items in left pane
        document.querySelectorAll('.nav-item[data-pane]').forEach(item => {
            item.addEventListener('click', (e) => {
                e.preventDefault();
                const pane = item.dataset.pane;
                const view = item.dataset.view;
                this.switchPane(pane, view);

                // Update active state
                document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
                item.classList.add('active');
            });
        });

        // Filter tabs in middle pane
        document.querySelectorAll('.filter-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const filter = btn.dataset.filter;
                this.filterContent(filter);

                document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
            });
        });

        // Search functionality
        const searchInput = document.getElementById('paneSearch');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                this.searchContent(e.target.value);
            });
        }

        // List item selection
        document.querySelectorAll('.list-item').forEach(item => {
            item.addEventListener('click', () => {
                const id = item.dataset.id;
                const type = item.dataset.type;
                this.selectItem(id, type);

                document.querySelectorAll('.list-item').forEach(i => i.classList.remove('active'));
                item.classList.add('active');
            });
        });
    }

    setupMobileNav() {
        const mobileNavBtns = document.querySelectorAll('.mobile-nav-btn');
        mobileNavBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                const pane = btn.dataset.pane;
                this.showMobilePane(pane);

                mobileNavBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
            });
        });
    }

    switchPane(pane, view) {
        this.currentPane = pane;

        // Update pane title
        const titleMap = {
            'dashboard': 'Dashboard Overview',
            'events': 'My Events',
            'trips': 'My Trips',
            'stays': 'My Stays',
            'wallet': 'Wallet Overview'
        };

        const titleEl = document.getElementById('paneTitle');
        if (titleEl) {
            titleEl.textContent = titleMap[pane] || pane;
        }

        // Load content based on pane
        this.loadPaneContent(pane, view);

        // On mobile, show middle pane
        if (this.isMobile) {
            this.showMobilePane('middle');
        }
    }

    loadPaneContent(pane, view) {
        // This would fetch content from the server
        // For now, we'll just toggle visibility of existing sections

        const sections = document.querySelectorAll('.list-section');
        sections.forEach(section => {
            const category = section.dataset.category;
            if (pane === 'events' && category === 'events') {
                section.style.display = 'block';
            } else if (pane === 'stays' && category === 'stays') {
                section.style.display = 'block';
            } else if (pane === 'dashboard') {
                section.style.display = 'block';
            } else {
                section.style.display = 'none';
            }
        });
    }

    filterContent(filter) {
        const sections = document.querySelectorAll('.list-section');
        sections.forEach(section => {
            const category = section.dataset.category;
            if (filter === 'all' || category === filter) {
                section.style.display = 'block';
            } else {
                section.style.display = 'none';
            }
        });
    }

    searchContent(query) {
        query = query.toLowerCase();
        const items = document.querySelectorAll('.list-item');

        items.forEach(item => {
            const title = item.querySelector('.item-title')?.textContent.toLowerCase() || '';
            const subtitle = item.querySelector('.item-subtitle')?.textContent.toLowerCase() || '';

            if (title.includes(query) || subtitle.includes(query)) {
                item.style.display = 'flex';
            } else {
                item.style.display = 'none';
            }
        });
    }

    selectItem(id, type) {
        this.selectedItem = { id, type };

        // Load detail view in right pane
        this.loadDetailView(id, type);

        // On mobile, show right pane
        if (this.isMobile) {
            this.showMobilePane('right');
        }
    }

    loadDetailView(id, type) {
        // Hide all detail views
        document.querySelectorAll('.detail-view').forEach(v => v.classList.remove('active'));

        // Show loading state
        const rightPane = document.querySelector('.right-pane-content');

        // Fetch and display detail
        // This would be an API call in production
        const viewId = `${type}DetailView`;
        const viewEl = document.getElementById(viewId);

        if (viewEl) {
            // For now, just show a placeholder
            viewEl.innerHTML = this.getDetailPlaceholder(type, id);
            viewEl.classList.add('active');
        }

        // Hide default view
        document.getElementById('defaultView')?.classList.remove('active');
    }

    getDetailPlaceholder(type, id) {
        return `
            <div class="detail-header">
                <h3>${type.charAt(0).toUpperCase() + type.slice(1)} Details</h3>
                <p>Loading details for ID: ${id}...</p>
            </div>
            <div class="detail-content">
                <p>Full details will be loaded here via API.</p>
            </div>
        `;
    }

    showMobilePane(pane) {
        const leftPane = document.querySelector('.left-pane');
        const middlePane = document.querySelector('.middle-pane');
        const rightPane = document.querySelector('.right-pane');

        leftPane?.classList.remove('active');
        middlePane?.classList.remove('active', 'hidden');
        rightPane?.classList.remove('active');

        if (pane === 'left') {
            leftPane?.classList.add('active');
            middlePane?.classList.add('hidden');
        } else if (pane === 'middle') {
            middlePane?.classList.remove('hidden');
        } else if (pane === 'right') {
            rightPane?.classList.add('active');
            middlePane?.classList.add('hidden');
        }
    }

    loadDefaultContent() {
        // Load initial dashboard content
        this.switchPane('dashboard', 'overview');
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    window.fanDashboard = new FanDashboard();
});

// Handle window resize
window.addEventListener('resize', () => {
    const isMobile = window.innerWidth <= 768;
    if (window.fanDashboard) {
        window.fanDashboard.isMobile = isMobile;
    }
});
