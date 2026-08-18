/** CSP-safe controller for dashboard tabs and registration cancellation. */
(function () {
    function closeModal(modal, confirm) {
        if (modal) modal.style.display = 'none';
        if (confirm) {
            confirm.disabled = false;
            confirm.textContent = 'Yes, Cancel';
        }
    }

    var cancelRef = null;
    var modal = document.getElementById('cancelModal');
    var text = document.getElementById('cancelModalText');
    var confirm = document.getElementById('confirmCancelBtn');

    document.querySelectorAll('.tab-btn').forEach(function (tab) {
        tab.addEventListener('click', function () {
            document.querySelectorAll('.tab-btn').forEach(function (item) { item.classList.remove('active'); });
            document.querySelectorAll('.tab-panel').forEach(function (panel) { panel.style.display = 'none'; });
            tab.classList.add('active');
            var panel = document.getElementById('tab-' + tab.dataset.tab);
            if (panel) panel.style.display = 'block';
        });
    });

    document.addEventListener('click', function (event) {
        var cancel = event.target.closest('[data-action="cancel-reg"]');
        if (cancel && modal && text) {
            cancelRef = cancel.dataset.regRef;
            text.textContent = 'Are you sure you want to cancel your registration for "' + cancel.dataset.eventName + '"? This action cannot be undone.';
            modal.style.display = 'flex';
        }
        if (event.target.closest('[data-action="close-modal"]') || event.target === modal) {
            cancelRef = null;
            closeModal(modal, confirm);
        }
    });

    if (confirm) confirm.addEventListener('click', function () {
        if (!cancelRef) return;
        confirm.disabled = true;
        confirm.textContent = 'Processing...';
        var csrf = document.querySelector('meta[name="csrf-token"]');
        fetch('/user/cancel-registration', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf ? csrf.content : ''},
            body: JSON.stringify({reg_ref: cancelRef})
        }).then(function (response) { return response.json(); }).then(function (data) {
            if (!data.success) throw new Error(data.error || 'Could not cancel registration');
            window.location.reload();
        }).catch(function (error) {
            window.alert('Error: ' + error.message);
            cancelRef = null;
            closeModal(modal, confirm);
        });
    });
})();