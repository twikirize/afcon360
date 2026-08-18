(function () {
    function copyValue(button) {
        const target = document.getElementById(button.dataset.copyTarget);
        if (!target || !navigator.clipboard) return;

        navigator.clipboard.writeText(target.value).then(function () {
            const originalText = button.textContent;
            button.textContent = "Copied";
            window.setTimeout(function () {
                button.textContent = originalText;
            }, 1500);
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll("[data-copy-target]").forEach(function (button) {
            button.addEventListener("click", function () {
                copyValue(button);
            });
        });

        document.querySelectorAll("form[data-confirm]").forEach(function (form) {
            form.addEventListener("submit", function (event) {
                if (!window.confirm(form.dataset.confirm)) {
                    event.preventDefault();
                }
            });
        });
    });
})();