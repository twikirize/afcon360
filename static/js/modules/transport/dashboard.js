/**
 * AFCON360 Transport Dashboard
 * Premium UI Interactions
 */

(function () {
    "use strict";

    // =========================================
    // DOM ELEMENTS
    // =========================================
    const sidebar = document.getElementById("sidebar");
    const sidebarToggle = document.getElementById("sidebarToggle");
    const mobileMenuToggle = document.getElementById("mobileMenuToggle");
    const mainContent = document.getElementById("mainContent");
    const loadingSpinner = document.getElementById("loading-spinner");

    let bookingsChartInstance = null; // prevent duplicate charts

    // =========================================
    // INITIALIZATION
    // =========================================
    document.addEventListener("DOMContentLoaded", function () {
        initSidebar();
        initMobileMenu();
        initSubmenus();
        initGlobalSearch();
        initNotifications();
        hideLoadingSpinner();
        initTooltips();
        initCharts();
        initAnalytics(); // moved analytics into main init
    });

    // =========================================
    // SIDEBAR FUNCTIONALITY
    // =========================================
    function initSidebar() {
        const sidebarState = localStorage.getItem("sidebarCollapsed");
        if (sidebarState === "true") {
            sidebar?.classList.add("collapsed");
        }

        sidebarToggle?.addEventListener("click", function (e) {
            e.preventDefault();
            sidebar?.classList.toggle("collapsed");
            localStorage.setItem(
                "sidebarCollapsed",
                sidebar?.classList.contains("collapsed")
            );
        });
    }

    function initMobileMenu() {
        mobileMenuToggle?.addEventListener("click", function () {
            sidebar?.classList.toggle("show");
        });

        document.addEventListener("click", function (e) {
            if (window.innerWidth <= 992) {
                if (
                    sidebar &&
                    !sidebar.contains(e.target) &&
                    mobileMenuToggle &&
                    !mobileMenuToggle.contains(e.target)
                ) {
                    sidebar.classList.remove("show");
                }
            }
        });
    }

    function initSubmenus() {
        document.querySelectorAll(".has-submenu > a").forEach((link) => {
            link.addEventListener("click", function (e) {
                e.preventDefault();
                this.parentElement.classList.toggle("open");
            });
        });
    }

    // =========================================
    // SEARCH FUNCTIONALITY
    // =========================================
    function initGlobalSearch() {
        const searchInput = document.getElementById("globalSearch");
        if (!searchInput) return;

        let searchTimeout;

        searchInput.addEventListener("input", function () {
            clearTimeout(searchTimeout);
            const query = this.value.trim();
            if (query.length < 2) return;

            searchTimeout = setTimeout(() => {
                performSearch(query);
            }, 300);
        });
    }

    function performSearch(query) {
        showSearchLoading?.();

        fetch(`/api/transport/search?q=${encodeURIComponent(query)}`)
            .then((res) => res.json())
            .then(displaySearchResults)
            .catch((err) => console.error("Search error:", err))
            .finally(() => hideSearchLoading?.());
    }

    function displaySearchResults(results) {
        const searchBox = document.querySelector(".search-box");
        if (!searchBox) return;

        let resultsDiv = document.getElementById("searchResults");

        if (!resultsDiv) {
            resultsDiv = document.createElement("div");
            resultsDiv.id = "searchResults";
            resultsDiv.className = "search-results-dropdown";
            searchBox.appendChild(resultsDiv);
        }

        if (!results.length) {
            resultsDiv.innerHTML =
                '<div class="no-results">No results found</div>';
        } else {
            resultsDiv.innerHTML = results
                .map(
                    (result) => `
                <a href="${result.url}" class="search-result-item">
                    <i class="fas fa-${result.icon}"></i>
                    <div class="result-content">
                        <div class="result-title">${result.title}</div>
                        <div class="result-subtitle">${result.subtitle}</div>
                    </div>
                </a>
            `
                )
                .join("");
        }

        resultsDiv.classList.add("show");

        document.addEventListener(
            "click",
            function closeSearch(e) {
                if (!searchBox.contains(e.target)) {
                    resultsDiv.classList.remove("show");
                    document.removeEventListener("click", closeSearch);
                }
            },
            { once: true }
        );
    }

    // =========================================
    // NOTIFICATIONS
    // =========================================
    function initNotifications() {
        loadNotifications();
        setInterval(loadNotifications, 30000);
    }

    function loadNotifications() {
        fetch("/api/transport/notifications/unread")
            .then((res) => res.json())
            .then((data) => {
                updateNotificationBadge(data.count);
                updateNotificationsList(data.notifications);
            })
            .catch((err) =>
                console.error("Failed to load notifications:", err)
            );
    }

    function updateNotificationBadge(count) {
        const badge = document.querySelector(".notification-badge");
        if (!badge) return;

        if (count > 0) {
            badge.textContent = count;
            badge.style.display = "block";
        } else {
            badge.style.display = "none";
        }
    }

    function updateNotificationsList(notifications) {
        const list = document.getElementById("notificationsList");
        if (!list) return;

        if (!notifications.length) {
            list.innerHTML =
                '<div class="no-notifications">No new notifications</div>';
            return;
        }

        list.innerHTML = notifications
            .map(
                (notif) => `
            <div class="notification-item ${
                notif.read ? "" : "unread"
            }" data-id="${notif.id}">
                <div class="notification-icon ${notif.type}">
                    <i class="fas fa-${notif.icon}"></i>
                </div>
                <div class="notification-content">
                    <div class="notification-title">${notif.title}</div>
                    <div class="notification-message">${notif.message}</div>
                    <div class="notification-time">${notif.time}</div>
                </div>
            </div>
        `
            )
            .join("");
    }

    // =========================================
    // ANALYTICS (CLEANED - NO DUPLICATION)
    // =========================================
    function initAnalytics() {
        const chartCanvas = document.getElementById("bookingsChart");
        if (!chartCanvas) return;

        fetch("/api/transport/analytics/summary")
            .then((response) => response.json())
            .then((data) => {
                if (!data.success) return;

                const summary = data.data.bookings;

                // Update KPIs
                document.getElementById("totalBookings").textContent =
                    AFCON.formatNumber(summary.total);
                document.getElementById("completionRate").textContent =
                    summary.completion_rate_pct + "%";
                document.getElementById("cancellationRate").textContent =
                    summary.cancellation_rate_pct + "%";

                // Destroy existing chart if exists
                if (bookingsChartInstance) {
                    bookingsChartInstance.destroy();
                }

                bookingsChartInstance = new Chart(
                    chartCanvas.getContext("2d"),
                    {
                        type: "doughnut",
                        data: {
                            labels: ["Completed", "Cancelled", "Other"],
                            datasets: [
                                {
                                    data: [
                                        summary.by_status.COMPLETED || 0,
                                        summary.by_status.CANCELLED || 0,
                                        summary.total -
                                            (summary.by_status.COMPLETED ||
                                                0) -
                                            (summary.by_status.CANCELLED || 0),
                                    ],
                                    backgroundColor: [
                                        "#4CAF50",
                                        "#F44336",
                                        "#FFC107",
                                    ],
                                },
                            ],
                        },
                        options: {
                            responsive: true,
                            plugins: {
                                title: {
                                    display: true,
                                    text: "Booking Status Breakdown",
                                },
                            },
                        },
                    }
                );
            })
            .catch((err) =>
                console.error("Error loading analytics summary:", err)
            );
    }

    // =========================================
    // LOADING SPINNER
    // =========================================
    function hideLoadingSpinner() {
        if (!loadingSpinner) return;
        loadingSpinner.classList.add("hidden");
        setTimeout(() => {
            loadingSpinner.style.display = "none";
        }, 300);
    }

    // =========================================
    // TOOLTIPS
    // =========================================
    function initTooltips() {
        document.querySelectorAll("[data-tooltip]").forEach((el) => {
            el.addEventListener("mouseenter", showTooltip);
            el.addEventListener("mouseleave", hideTooltip);
        });
    }

    function showTooltip(e) {
        const el = e.target;
        const tooltip = document.createElement("div");
        tooltip.className = "custom-tooltip";
        tooltip.textContent = el.dataset.tooltip;
        document.body.appendChild(tooltip);

        const rect = el.getBoundingClientRect();
        tooltip.style.left =
            rect.left + rect.width / 2 - tooltip.offsetWidth / 2 + "px";
        tooltip.style.top =
            rect.top - tooltip.offsetHeight - 10 + "px";

        el._tooltip = tooltip;
    }

    function hideTooltip(e) {
        e.target._tooltip?.remove();
        delete e.target._tooltip;
    }

    // =========================================
    // CHART FALLBACK
    // =========================================
    function initCharts() {
        if (typeof Chart === "undefined") {
            console.warn("Chart.js not loaded");
        }
    }

    // =========================================
    // UTILITIES
    // =========================================
    function formatNumber(num) {
        return new Intl.NumberFormat().format(num);
    }

    function formatCurrency(amount) {
        return new Intl.NumberFormat("en-US", {
            style: "currency",
            currency: "USD",
        }).format(amount);
    }

    function formatDate(date) {
        return new Intl.DateTimeFormat("en-US", {
            year: "numeric",
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        }).format(new Date(date));
    }

    function timeAgo(date) {
        const seconds = Math.floor(
            (new Date() - new Date(date)) / 1000
        );

        const intervals = {
            year: 31536000,
            month: 2592000,
            week: 604800,
            day: 86400,
            hour: 3600,
            minute: 60,
            second: 1,
        };

        for (let [unit, secondsInUnit] of Object.entries(intervals)) {
            const interval = Math.floor(seconds / secondsInUnit);
            if (interval >= 1) {
                return (
                    interval +
                    " " +
                    unit +
                    (interval === 1 ? "" : "s") +
                    " ago"
                );
            }
        }

        return "just now";
    }

    window.AFCON = {
        formatNumber,
        formatCurrency,
        formatDate,
        timeAgo,
    };
})();
