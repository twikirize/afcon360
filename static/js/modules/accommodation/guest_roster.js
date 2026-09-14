/* ============================================================ */
/* GUEST ROSTER - DELEGATION FORM                                */
/* ============================================================ */

(function() {
    var form = document.getElementById('delegateForm');
    if (!form) return;

    var feedback = document.getElementById('delegateFeedback');
    var emailInput = document.getElementById('delegateEmail');

    function show(message, isError) {
        if (!feedback) return;
        feedback.className = isError
            ? 'alert alert-danger py-2 mb-0'
            : 'alert alert-success py-2 mb-0';
        feedback.textContent = message;
        feedback.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    form.addEventListener('submit', function(e) {
        e.preventDefault();

        var email = (emailInput && emailInput.value.trim()) || '';
        if (!email) {
            show('Enter the email address of the person you want to delegate to.', true);
            return;
        }

        var body = new FormData();
        body.append('email', email);
        body.append('duration_hours', '168');
        body.append('reason', 'Roster management delegated from the booking roster page');
        var tokenInput = form.querySelector('input[name="csrf_token"]');
        if (tokenInput) body.append('csrf_token', tokenInput.value);

        var button = form.querySelector('button[type="submit"]');
        if (button) {
            button.disabled = true;
            button.textContent = 'Delegating...';
        }

        fetch(form.action, { method: 'POST', body: body, headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(function(response) {
                return response.json().catch(function() {
                    return { success: false, error: 'Unexpected response. Please try again.' };
                }).then(function(data) {
                    return { ok: response.ok, data: data };
                });
            })
            .then(function(result) {
                if (result.ok && result.data.success) {
                    show('Roster management delegated. They can now manage this guest list.', false);
                    if (emailInput) emailInput.value = '';
                } else {
                    show(result.data.error || 'Delegation could not be created.', true);
                }
            })
            .catch(function() {
                show('Delegation request failed. Please try again.', true);
            })
            .finally(function() {
                if (button) {
                    button.disabled = false;
                    button.textContent = 'Delegate';
                }
            });
    });
})();

/* ============================================================ */
/* GUEST ROSTER - TRANSPORT COORDINATION (STAGE 5, TASK1)        */
/* Select-only: the operator picks from available booked transport */
/* ============================================================ */

(function() {
    var modalEl = document.getElementById('assignTransportModal');
    if (!modalEl) return;

    var form = document.getElementById('assignTransportForm');
    var guestLabel = document.getElementById('assignTransportGuest');
    var select = document.getElementById('transportSelect');
    var emptyBox = document.getElementById('transportEmpty');
    var submitBtn = document.getElementById('assignTransportSubmit');
    var paneUrl = form.getAttribute('data-pane-url');
    var availableUrl = form.getAttribute('data-available-url');
    var bookUrl = form.getAttribute('data-book-url') || '';
    var currentRegistrationId = null;
    var currentAssignUrl = null;
    var availableItems = [];
    var accommodationRef = form.getAttribute('data-accomm-ref') || '';
    var selectedRef = null;
    var modalGuestName = '';

    var modal = new bootstrap.Modal(modalEl, { backdrop: 'static' });

    var confirmModalEl = document.getElementById('confirmTransportModal');
    var confirmDetails = document.getElementById('confirmTransportDetails');
    var confirmBackBtn = document.getElementById('confirmTransportBack');
    var confirmSubmitBtn = document.getElementById('confirmTransportSubmit');
    var confirmModal = confirmModalEl ? new bootstrap.Modal(confirmModalEl, { backdrop: 'static' }) : null;
    var tokenInput = form.querySelector('input[name="csrf_token"]');
    var csrfToken = tokenInput ? tokenInput.value : '';

    function csrfHeaders() {
        return { 'X-CSRFToken': csrfToken, 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' };
    }

    function fmt(iso) {
        if (!iso) return '';
        return iso.replace('T', ' ').slice(0, 16);
    }

    /* Read-side pane: fill the assigned-booking detail line for each guest. */
    function loadPane() {
        if (!paneUrl) return;

        fetch(paneUrl, { method: 'GET', headers: csrfHeaders() })
            .then(function(response) { return response.json(); })
            .then(function(data) {
                if (!data.success || !Array.isArray(data.items)) return;
                data.items.forEach(function(item) {
                    var detail = document.querySelector('[data-registration-id="' + item.registration_id + '"] [data-transport-detail]');
                    if (!detail || !item.transport) return;
                    var t = item.transport;
                    var parts = [];
                    if (t.booking_ref) parts.push(t.booking_ref);
                    if (t.vehicle) parts.push('Vehicle ' + t.vehicle);
                    if (t.pickup_time) parts.push(fmt(t.pickup_time));
                    detail.textContent = parts.join(' · ') || 'Assigned';
                });
            })
            .catch(function() { /* detail lines stay empty on transient errors */ });
    }

    function populateSelect(items) {
        select.innerHTML = '';
        items.forEach(function(t) {
            var opt = document.createElement('option');
            opt.value = t.booking_ref || '';
            var label = t.booking_ref || 'Unknown';
            if (t.status) label += ' · ' + t.status;
            if (t.pickup_time) label += ' · ' + fmt(t.pickup_time);
            if (t.pickup) label += ' · ' + t.pickup;
            opt.textContent = label;
            select.appendChild(opt);
        });
    }

    function showAssignable(countTotal, items, assignable) {
        emptyBox.innerHTML = '';
        if (countTotal === 0) {
            // State 1: no target resources exist at all → offer booking nav.
            var none = document.createElement('div');
            none.className = 'small text-muted mb-2';
            none.textContent = 'You have no booked transport yet. Book transport first, then return here to select it.';
            emptyBox.appendChild(none);
            var link = document.createElement('a');
            link.href = bookUrl || '#';
            link.className = 'btn btn-sm btn-outline-primary';
            link.textContent = 'Book Transport';
            emptyBox.appendChild(link);
            return;
        }
        if (items.length === 0) {
            // State 2: resources exist but none is eligible.
            var stuck = document.createElement('div');
            stuck.className = 'small text-muted mb-2';
            stuck.textContent = 'You have ' + countTotal + ' transport booking(s), but none is currently assignable (only ' +
                (assignable || []).join(' / ') + ' bookings can be assigned).';
            emptyBox.appendChild(stuck);
            var link2 = document.createElement('a');
            link2.href = bookUrl || '#';
            link2.className = 'btn btn-sm btn-outline-primary';
            link2.textContent = 'Book Transport';
            emptyBox.appendChild(link2);
            return;
        }
        // State 3: eligible resources → populate the select.
        populateSelect(items);
        select.hidden = false;
        submitBtn.hidden = false;
        submitBtn.disabled = false;
    }

    function renderUnavailable(message) {
        emptyBox.innerHTML = '';
        availableItems = [];
        var p = document.createElement('p');
        p.className = 'small text-danger mb-2';
        p.textContent = message || 'Available transport could not be loaded.';
        emptyBox.appendChild(p);
        emptyBox.hidden = false;
        select.hidden = true;
        submitBtn.hidden = true;
    }

    function loadAvailable() {
        if (!availableUrl) return;
        // Fresh read on every modal open so a newly booked resource appears
        // immediately after the return journey.
        submitBtn.disabled = true;
        fetch(availableUrl, { method: 'GET', headers: csrfHeaders() })
            .then(function(response) { return response.json(); })
            .then(function(data) {
                if (!data.success || !Array.isArray(data.items)) {
                    renderUnavailable(data.error || 'Available transport could not be loaded.');
                    return;
                }
                availableItems = data.items.slice();
                if (data.book_url) bookUrl = data.book_url;
                emptyBox.hidden = true;
                select.hidden = true;
                submitBtn.hidden = true;
                showAssignable(data.count_total, data.items, data.assignable);
            })
            .catch(function() {
                renderUnavailable('Available transport could not be loaded. Please try again.');
            });
    }

    function openAssign(button) {
        currentRegistrationId = button.closest('[data-registration-id]').getAttribute('data-registration-id');
        currentAssignUrl = button.getAttribute('data-assign-url');
        modalGuestName = button.getAttribute('data-guest-name') || '';
        selectedRef = null;
        guestLabel.textContent = 'Assigning transport for ' + modalGuestName;
        form.classList.remove('was-validated');
        modal.show();
        loadAvailable();
    }

    document.querySelectorAll('[data-assign-transport]').forEach(function(button) {
        button.addEventListener('click', function() { openAssign(button); });
    });

    function addDetailRow(label, value) {
        if (!confirmDetails) return;
        var dt = document.createElement('dt');
        dt.className = 'col-sm-4 text-muted small';
        dt.textContent = label;
        var dd = document.createElement('dd');
        dd.className = 'col-sm-8 small';
        dd.textContent = value || '—';
        confirmDetails.appendChild(dt);
        confirmDetails.appendChild(dd);
    }

    function currentItem() {
        if (!selectedRef) return null;
        for (var i = 0; i < availableItems.length; i++) {
            if (availableItems[i].booking_ref === selectedRef) return availableItems[i];
        }
        return null;
    }

    function openConfirm() {
        var item = currentItem();
        if (!confirmDetails || !confirmModal || !item) return;
        confirmDetails.innerHTML = '';
        addDetailRow('Customer', modalGuestName);
        addDetailRow('Accommodation booking', accommodationRef);
        addDetailRow('Transport booking', item.booking_ref || '—');
        addDetailRow('Vehicle', item.vehicle || '—');
        addDetailRow('Driver', item.driver || '—');
        var when = item.pickup_time ? fmt(item.pickup_time) : '';
        addDetailRow('Pickup', [item.pickup, when].filter(Boolean).join(' · ') || '—');
        addDetailRow('Drop-off', item.dropoff || '—');
        modal.hide();
        confirmModal.show();
    }

    function setConfirmSubmitting(active) {
        if (!confirmSubmitBtn) return;
        confirmSubmitBtn.disabled = active;
        confirmSubmitBtn.textContent = active ? 'Confirming…' : 'Confirm assignment';
    }

    function performAssign() {
        if (!currentRegistrationId || !selectedRef) return;
        setConfirmSubmitting(true);
        fetch(currentAssignUrl, {
            method: 'POST',
            headers: csrfHeaders(),
            body: JSON.stringify({ transport_booking_ref: selectedRef })
        })
            .then(function(response) {
                return response.json().catch(function() {
                    return { success: false, error: 'Unexpected response. Please try again.' };
                }).then(function(data) {
                    return { ok: response.ok, data: data };
                });
            })
            .then(function(result) {
                if (result.ok && result.data.success) {
                    window.location.reload();
                } else {
                    alert(result.data.error || 'The transport assignment could not be completed.');
                    if (confirmModal) confirmModal.hide();
                    modal.show();
                }
            })
            .catch(function() {
                alert('The transport assignment request failed. Please try again.');
                if (confirmModal) confirmModal.hide();
                modal.show();
            })
            .finally(function() { setConfirmSubmitting(false); });
    }

    form.addEventListener('submit', function(e) {
        e.preventDefault();
        if (!form.checkValidity()) {
            form.classList.add('was-validated');
            return;
        }
        if (!currentRegistrationId || !select.value) return;
        selectedRef = select.value;
        openConfirm();
    });

    if (confirmSubmitBtn) confirmSubmitBtn.addEventListener('click', performAssign);
    if (confirmBackBtn && confirmModal) {
        confirmBackBtn.addEventListener('click', function() {
            confirmModal.hide();
            modal.show();
        });
    }
    if (confirmModal && confirmModalEl) {
        confirmModalEl.addEventListener('hidden.bs.modal', function() {
            if (modal && !confirmSubmitBtn.disabled) modal.show();
        });
    }

    loadPane();
})();