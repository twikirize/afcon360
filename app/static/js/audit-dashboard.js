// Audit Dashboard JavaScript
document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl)
    });

    // Initialize popovers
    var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'))
    var popoverList = popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl)
    });

    // Real-time updates for audit dashboard
    function updateAuditStats() {
        fetch('/api/audit/stats')
            .then(response => response.json())
            .then(data => {
                // Update stats cards
                document.querySelectorAll('.stat-card').forEach(card => {
                    const statType = card.dataset.stat;
                    if (data[statType] !== undefined) {
                        const numberElement = card.querySelector('.stat-number');
                        if (numberElement) {
                            numberElement.textContent = data[statType];
                        }
                    }
                });
            })
            .catch(error => console.error('Error fetching audit stats:', error));
    }

    // Auto-refresh every 30 seconds if on dashboard
    if (window.location.pathname.includes('dashboard')) {
        setInterval(updateAuditStats, 30000);
    }

    // Filter audit table
    const filterButtons = document.querySelectorAll('.audit-filter');
    filterButtons.forEach(button => {
        button.addEventListener('click', function() {
            const filterValue = this.dataset.filter;

            // Update active button
            filterButtons.forEach(btn => btn.classList.remove('active'));
            this.classList.add('active');

            // Filter table rows
            const tableRows = document.querySelectorAll('.audit-table tbody tr');
            tableRows.forEach(row => {
                const status = row.dataset.status;
                if (filterValue === 'all' || status === filterValue) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            });
        });
    });

    // Export functionality
    const exportButtons = document.querySelectorAll('.export-btn');
    exportButtons.forEach(button => {
        button.addEventListener('click', function() {
            const format = this.dataset.format;
            const tableId = this.dataset.table;

            alert(`Exporting ${tableId} as ${format.toUpperCase()}...`);
            // In production, this would make an API call to generate the export
        });
    });

    // Search functionality for audit tables
    const searchInputs = document.querySelectorAll('.audit-search');
    searchInputs.forEach(input => {
        input.addEventListener('input', function() {
            const searchTerm = this.value.toLowerCase();
            const tableId = this.dataset.table;
            const table = document.getElementById(tableId);

            if (!table) return;

            const rows = table.querySelectorAll('tbody tr');
            rows.forEach(row => {
                const text = row.textContent.toLowerCase();
                if (text.includes(searchTerm)) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            });
        });
    });

    // Confirmation modals for sensitive actions
    const confirmButtons = document.querySelectorAll('[data-confirm]');
    confirmButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            const message = this.dataset.confirm;
            if (!confirm(message)) {
                e.preventDefault();
            }
        });
    });

    // Load charts if Chart.js is available
    if (typeof Chart !== 'undefined') {
        loadAuditCharts();
    }

    function loadAuditCharts() {
        // This would load actual chart data from an API
        console.log('Chart.js loaded - would initialize charts here');
    }
});
