/**
 * Base Template UI Functionality
 * Handles layout-level interactions only
 */

(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        initSidebar();
        initRefreshButton();
        initFlashMessages();
    });

    // =========================================
    // SIDEBAR
    // =========================================
    function initSidebar() {
        const sidebar = document.getElementById("sidebar");
        const toggle = document.getElementById("sidebarToggle");
        const overlay = document.getElementById("sidebarOverlay");

        if (!sidebar || !toggle) return;

        toggle.addEventListener("click", function () {
            sidebar.classList.toggle("open");

            if (overlay) {
                overlay.style.display =
                    sidebar.classList.contains("open") ? "block" : "none";
            }
        });

        if (overlay) {
            overlay.addEventListener("click", function () {
                sidebar.classList.remove("open");
                overlay.style.display = "none";
            });
        }
    }

    // =========================================
    // REFRESH BUTTON
    // =========================================
    function initRefreshButton() {
        const refreshBtn = document.getElementById("refreshBtn");
        if (!refreshBtn) return;

        refreshBtn.addEventListener("click", function () {
            refreshBtn.style.transition = "transform 0.4s ease";
            refreshBtn.style.transform = "rotate(360deg)";

            setTimeout(function () {
                refreshBtn.style.transform = "";
                window.location.reload();
            }, 400);
        });
    }

    // =========================================
    // AUTO-DISMISS FLASH MESSAGES
    // =========================================
    function initFlashMessages() {
        const alerts = document.querySelectorAll(".alert[data-timeout]");
        if (!alerts.length) return;

        alerts.forEach(function (alert) {
            const timeout = parseInt(alert.dataset.timeout, 10) || 5000;

            setTimeout(function () {
                alert.style.transition = "opacity 0.4s ease";
                alert.style.opacity = "0";

                setTimeout(function () {
                    alert.remove();
                }, 400);
            }, timeout);
        });
    }

})();
