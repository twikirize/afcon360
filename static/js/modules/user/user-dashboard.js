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

    function activateTab(tab) {
        document.querySelectorAll('.tab-btn').forEach(function (item) { item.classList.remove('active'); });
        document.querySelectorAll('.tab-panel').forEach(function (panel) { panel.style.display = 'none'; });
        tab.classList.add('active');
        var panel = document.getElementById('tab-' + tab.dataset.tab);
        if (panel) panel.style.display = 'block';
    }

    document.querySelectorAll('.tab-btn').forEach(function (tab) {
        tab.addEventListener('click', function () { activateTab(tab); });
    });

    var initialTab = document.querySelector('.tab-btn.active');
    if (initialTab) activateTab(initialTab);

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

    // ── Host an Event / Become an Organizer flow (attendee dashboard) ────────
    var orgBtn = document.getElementById('hostEventBtn');
    var orgModal = document.getElementById('orgEligibilityModal');
    var orgTitle = document.getElementById('orgEligibilityTitle');
    var orgBody = document.getElementById('orgEligibilityBody');
    var orgConfirm = document.getElementById('orgConfirmBtn');
    var orgForm = document.getElementById('becomeOrganizerForm');

    function openOrgModal(title, html, showConfirm) {
        if (!orgModal) return;
        if (orgTitle) orgTitle.textContent = title;
        if (orgBody) orgBody.innerHTML = html;
        if (orgConfirm) orgConfirm.style.display = showConfirm ? 'inline-block' : 'none';
        orgModal.style.display = 'flex';
    }

    function closeOrgModal() {
        if (orgModal) orgModal.style.display = 'none';
    }

    if (orgBtn) orgBtn.addEventListener('click', function () {
        orgBtn.disabled = true;
        orgBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Checking eligibility…';
        fetch('/events/api/become-organizer/eligibility', {
            headers: {'X-Requested-With': 'XMLHttpRequest'}
        }).then(function (r) { return r.json(); }).then(function (data) {
            if (data.already_organizer) {
                openOrgModal('Already an Organizer',
                    '<p style="margin:0;">You already have an organizer profile. Continue to your Organizer Dashboard to create and manage events.</p>', false);
                if (orgConfirm) {
                    orgConfirm.style.display = 'inline-block';
                    orgConfirm.textContent = 'Open Organizer Dashboard';
                    orgConfirm.onclick = function () { window.location.href = '/events/organizer/dashboard'; };
                }
                return;
            }
            if (data.eligible) {
                openOrgModal('Host Your Own Event',
                    '<p style="margin:0 0 8px;">Your account verification and attendance history qualify you to become an organizer. ' +
                    'Confirm and we’ll create your event organizer dashboard — your attendee history is preserved — then take you there to create and manage events.</p>', true);
                if (orgConfirm) orgConfirm.textContent = 'Create Organizer Dashboard';
                return;
            }
            var reasons = (data.reasons || []).map(function (r) { return '<li>' + r + '</li>'; }).join('');
            openOrgModal('Almost There',
                '<p style="margin:0 0 8px;">You need to complete the following before you can host events:</p>' +
                '<ul style="margin:0; padding-left:18px;">' + reasons + '</ul>', false);
        }).catch(function () {
            openOrgModal('Something went wrong', '<p style="margin:0;">Could not check eligibility. Please try again.</p>', false);
        }).finally(function () {
            orgBtn.disabled = false;
            orgBtn.innerHTML = '<i class="fas fa-rocket me-1"></i> Host an Event';
        });
    });

    if (orgConfirm) orgConfirm.addEventListener('click', function () {
        if (orgForm) orgForm.submit();
    });

    if (orgModal) {
        orgModal.addEventListener('click', function (e) {
            if (e.target === orgModal || e.target.closest('[data-action="close-org-modal"]')) closeOrgModal();
        });
    }
})();