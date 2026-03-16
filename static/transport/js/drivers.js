// Drivers-specific functionality
(function() {
    "use strict";

    document.addEventListener("DOMContentLoaded", () => {
        if (!document.querySelector('.drivers-grid')) return; // not drivers page

        initDriverFilters();
        initDriverCards();
    });

    function initDriverFilters() {
        const filterForm = document.getElementById('driverFilters');
        if (!filterForm) return;

        filterForm.addEventListener('submit', (e) => {
            e.preventDefault();
            applyFilters();
        });
    }

    function initDriverCards() {
        document.querySelectorAll('.driver-card .btn-toggle').forEach(btn => {
            btn.addEventListener('click', function() {
                const driverId = this.dataset.driverId;
                toggleDriverOnline(driverId);
            });
        });
    }

    function toggleDriverOnline(driverId) {
        fetch(`/api/transport/drivers/${driverId}/toggle-online`, { method: 'POST' })
            .then(r => r.json())
            .then(d => {
                if (d.success) window.location.reload();
            });
    }

    function applyFilters() {
        // filter logic
    }
})();