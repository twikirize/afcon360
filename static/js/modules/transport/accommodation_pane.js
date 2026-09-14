/* ============================================================ */
/* BOOKING SHOW - ACCOMMODATION COORDINATION PANE (STAGE 5 TASK2) */
/* Select-only: the operator picks from available booked accommodation */
/* ============================================================ */

(function() {
    var pane = document.getElementById('accommodationPane');
    if (!pane) return;

    var content = document.getElementById('accommodationPaneContent');
    if (!content) return;

    var paneUrl = pane.getAttribute('data-pane-url');
    var availableUrl = pane.getAttribute('data-available-url');
    var csrfToken = pane.getAttribute('data-csrf') || '';
    var bookingRef = pane.getAttribute('data-booking-ref') || '';
    var bookUrl = pane.getAttribute('data-book-url') || '/accommodation/';

    /* Two-phase confirmation modal state. */
    var availableItemsCache = [];
    var pendingAssign = null;
    var confirmModalEl = document.getElementById('confirmAccommodationModal');
    var confirmDetailsEl = document.getElementById('confirmAccommodationDetails');
    var confirmSubmitBtn = document.getElementById('confirmAccommodationSubmit');
    var confirmBackBtn = document.getElementById('confirmAccommodationBack');

    function csrfHeaders() {
        return { 'X-CSRFToken': csrfToken, 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' };
    }

    function rowStyle() {
        return 'border:1px solid var(--border);border-radius:8px;padding:10px 12px;margin-bottom:10px;';
    }

    function btnStyle(kind) {
        var base = 'display:inline-flex;align-items:center;gap:6px;border:none;border-radius:6px;padding:6px 10px;font-size:0.78rem;cursor:pointer;';
        if (kind === 'primary') return base + 'background:var(--accent,#3b82f6);color:#fff;';
        if (kind === 'danger') return base + 'background:transparent;color:var(--red,#ef4444);border:1px solid var(--border);';
        return base + 'background:var(--bg-elevated);color:var(--text-primary);border:1px solid var(--border);';
    }

    function selectStyle() {
        return 'width:100%;padding:6px 8px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text-primary);font-size:0.8rem;margin:6px 0;';
    }

    function fmt(iso) {
        if (!iso) return '';
        return iso.replace('T', ' ').slice(0, 16);
    }

    function summaryFor(item) {
        var a = item.accommodation;
        if (!a || !a.booking_ref) return 'No accommodation assigned.';
        var parts = [a.booking_ref];
        if (a.property) parts.push('Property ' + a.property);
        if (a.room_type) parts.push(a.room_type);
        var dates = [];
        if (a.check_in) dates.push(fmt(a.check_in));
        if (a.check_out) dates.push(fmt(a.check_out));
        if (dates.length) parts.push(dates.join(' → '));
        return parts.join(' · ');
    }

    /* Element factory helpers for the inline assign box. */
    function boxMessage(className) {
        var el = document.createElement('div');
        el.className = className || 'text-muted small';
        el.style = 'font-size:0.78rem;margin:4px 0;';
        return el;
    }

    function bookLink() {
        var a = document.createElement('a');
        a.href = bookUrl;
        a.textContent = 'Book Accommodation';
        a.style = 'color:var(--accent,#3b82f6);';
        return a;
    }

    /* Populate the assign box from the available accommodation endpoint.
       Three states: none exist → offer booking nav; exist but none eligible →
       explain; eligible → show the select. */
    function loadAvailable(box, selectEl, confirmBtn, hint) {
        var assignables = [];
        if (!availableUrl) {
            hint.textContent = 'Available accommodation could not be loaded.';
            return;
        }
        confirmBtn.disabled = true;
        selectEl.innerHTML = '<option value="">Loading available accommodation…</option>';

        fetch(availableUrl, { method: 'GET', headers: csrfHeaders() })
            .then(function(response) { return response.json(); })
            .then(function(data) {
                hint.innerHTML = '';
                if (!data.success || !Array.isArray(data.items)) {
                    var err = boxMessage('text-danger');
                    err.textContent = data.error || 'Available accommodation could not be loaded.';
                    hint.appendChild(err);
                    return;
                }
                if (data.book_url) bookUrl = data.book_url;
                availableItemsCache = data.items || [];
                assignables = data.assignable || [];
                if (data.count_total === 0) {
                    // State 1: no target resources exist.
                    var none = boxMessage();
                    none.textContent = 'You have no booked accommodation yet. Book accommodation first, then return here to select it.';
                    hint.appendChild(none);
                    hint.appendChild(bookLink());
                    return;
                }
                if (data.items.length === 0) {
                    // State 2: resources exist but none eligible.
                    var stuck = boxMessage();
                    stuck.textContent = 'You have ' + data.count_total + ' accommodation booking(s), but none is currently assignable (only ' +
                        assignables.join(' / ') + ' bookings can be assigned).';
                    hint.appendChild(stuck);
                    hint.appendChild(bookLink());
                    return;
                }
                // State 3: eligible resources → populate the select.
                data.items.forEach(function(a) {
                    var opt = document.createElement('option');
                    opt.value = a.booking_ref || '';
                    var label = a.booking_ref || 'Unknown';
                    if (a.status) label += ' · ' + a.status;
                    if (a.property) label += ' · ' + a.property;
                    if (a.check_in) label += ' · ' + fmt(a.check_in);
                    opt.textContent = label;
                    selectEl.appendChild(opt);
                });
                selectEl.hidden = false;
                confirmBtn.hidden = false;
                confirmBtn.disabled = false;
            })
            .catch(function() {
                hint.innerHTML = '';
                var err = boxMessage('text-danger');
                err.textContent = 'Available accommodation could not be loaded. Please try again.';
                hint.appendChild(err);
            });
    }

    function renderRow(item) {
        var card = document.createElement('div');
        card.style = rowStyle();

        var head = document.createElement('div');
        head.style = 'display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:4px;';
        var name = document.createElement('strong');
        name.style = 'font-size:0.85rem;color:var(--text-primary);';
        name.textContent = item.name || 'Passenger';
        var badge = document.createElement('span');
        badge.style = 'font-size:0.68rem;padding:2px 8px;border-radius:10px;background:var(--bg-elevated);color:var(--text-muted);border:1px solid var(--border);text-transform:capitalize;';
        badge.textContent = item.status || '';
        head.appendChild(name);
        head.appendChild(badge);
        card.appendChild(head);

        var summary = document.createElement('div');
        summary.style = 'font-size:0.78rem;color:var(--text-muted);margin-bottom:8px;';
        summary.textContent = summaryFor(item);
        card.appendChild(summary);

        var actions = document.createElement('div');
        actions.style = 'display:flex;gap:8px;align-items:center;';

        var assign = document.createElement('button');
        assign.type = 'button';
        assign.style = btnStyle('primary');
        assign.textContent = item.accommodation ? 'Reassign' : 'Assign';
        assign.dataset.passengerId = item.passenger_id;
        assign.dataset.assignUrl = item.assign_url;

        var box = document.createElement('div');
        box.style = 'display:none;margin-top:8px;';

        var selectEl = document.createElement('select');
        selectEl.name = 'accommodation_booking_ref';
        selectEl.style = selectStyle();

        var boxErr = document.createElement('div');
        boxErr.style = 'font-size:0.75rem;color:var(--red,#ef4444);margin:4px 0;';

        var boxConfirm = document.createElement('button');
        boxConfirm.type = 'button';
        boxConfirm.style = btnStyle('primary');
        boxConfirm.textContent = 'Confirm';

        var boxCancel = document.createElement('button');
        boxCancel.type = 'button';
        boxCancel.style = btnStyle();
        boxCancel.textContent = 'Cancel';

        var hint = document.createElement('div');
        hint.style = 'font-size:0.72rem;color:var(--text-muted);margin-top:6px;';

        box.appendChild(selectEl);
        box.appendChild(boxErr);
        box.appendChild(boxConfirm);
        box.appendChild(boxCancel);
        box.appendChild(hint);

        actions.appendChild(assign);
        card.appendChild(actions);
        card.appendChild(box);

        var unassign = null;
        if (item.accommodation) {
            unassign = document.createElement('button');
            unassign.type = 'button';
            unassign.style = btnStyle('danger');
            unassign.textContent = 'Unassign';
            unassign.dataset.passengerId = item.passenger_id;
            unassign.dataset.unassignUrl = item.unassign_url;
            actions.appendChild(unassign);
        }

        assign.addEventListener('click', function() {
            var opening = box.style.display !== 'block';
            box.style.display = opening ? 'block' : 'none';
            boxErr.textContent = '';
            if (opening) {
                loadAvailable(box, selectEl, boxConfirm, hint);
            }
        });
        boxCancel.addEventListener('click', function() { box.style.display = 'none'; });
        boxConfirm.addEventListener('click', function() {
            var ref = selectEl.value.trim();
            if (!ref) { boxErr.textContent = 'Select an accommodation booking from the list.'; return; }
            var entry = null;
            for (var i = 0; i < availableItemsCache.length; i++) {
                if (availableItemsCache[i].booking_ref === ref) { entry = availableItemsCache[i]; break; }
            }
            if (!entry) { boxErr.textContent = 'The selected accommodation booking is no longer available. Please reload.'; return; }
            pendingAssign = { url: assign.dataset.assignUrl, ref: ref, passengerName: item.name || 'Passenger', errorEl: boxErr };
            openConfirmModal(item, entry);
        });

        if (unassign) {
            unassign.addEventListener('click', function() {
                if (!window.confirm('Release the accommodation assignment for this passenger?')) return;
                unassign.disabled = true;
                fetch(unassign.dataset.unassignUrl, {
                    method: 'POST',
                    headers: csrfHeaders()
                })
                    .then(function(response) { return response.json(); })
                    .then(function(data) {
                        if (data.success) { window.location.reload(); return; }
                        window.alert(data.error || 'The accommodation unassignment could not be completed.');
                        unassign.disabled = false;
                    })
                    .catch(function() {
                        window.alert('The accommodation unassignment request failed. Please try again.');
                        unassign.disabled = false;
                    });
            });
        }

        content.appendChild(card);
    }

    /* Confirmation modal for the two-phase accommodation assignment. */
    function modalRow(label, value) {
        var row = document.createElement('div');
        row.style = 'display:flex;justify-content:space-between;gap:12px;padding:6px 0;border-bottom:1px solid var(--border);';
        var l = document.createElement('span');
        l.style = 'color:var(--text-muted);';
        l.textContent = label;
        var v = document.createElement('span');
        v.style = 'text-align:right;color:var(--text-primary);';
        v.textContent = value || '—';
        row.appendChild(l);
        row.appendChild(v);
        return row;
    }

    function openConfirmModal(passengerItem, entry) {
        if (!confirmDetailsEl || !confirmModalEl) return;
        confirmDetailsEl.innerHTML = '';
        var dates = [];
        if (entry.check_in) dates.push(fmt(entry.check_in));
        if (entry.check_out) dates.push(fmt(entry.check_out));
        confirmDetailsEl.appendChild(modalRow('Passenger', passengerItem.name || 'Passenger'));
        confirmDetailsEl.appendChild(modalRow('Transport booking', bookingRef));
        confirmDetailsEl.appendChild(modalRow('Accommodation booking', entry.booking_ref || '—'));
        confirmDetailsEl.appendChild(modalRow('Property', entry.property || '—'));
        confirmDetailsEl.appendChild(modalRow('Room type', entry.room_type || '—'));
        confirmDetailsEl.appendChild(modalRow('Stay', dates.join(' → ') || '—'));
        confirmDetailsEl.appendChild(modalRow('Status', entry.status || '—'));
        confirmModalEl.style.display = 'flex';
    }

    function setConfirmSubmitting(active) {
        if (!confirmSubmitBtn) return;
        confirmSubmitBtn.disabled = active;
        confirmSubmitBtn.textContent = active ? 'Confirming…' : 'Confirm assignment';
    }

    function performAccommodationAssign() {
        if (!pendingAssign) return;
        setConfirmSubmitting(true);
        fetch(pendingAssign.url, {
            method: 'POST',
            headers: csrfHeaders(),
            body: JSON.stringify({ accommodation_booking_ref: pendingAssign.ref })
        })
            .then(function(response) {
                return response.json().catch(function() {
                    return { success: false, error: 'Unexpected response. Please try again.' };
                });
            })
            .then(function(data) {
                if (data.success) { window.location.reload(); return; }
                if (pendingAssign.errorEl) pendingAssign.errorEl.textContent = data.error || 'The accommodation assignment could not be completed.';
                if (confirmModalEl) confirmModalEl.style.display = 'none';
                setConfirmSubmitting(false);
            })
            .catch(function() {
                if (pendingAssign.errorEl) pendingAssign.errorEl.textContent = 'The accommodation assignment request failed. Please try again.';
                if (confirmModalEl) confirmModalEl.style.display = 'none';
                setConfirmSubmitting(false);
            });
    }

    if (confirmSubmitBtn) confirmSubmitBtn.addEventListener('click', performAccommodationAssign);
    if (confirmBackBtn) confirmBackBtn.addEventListener('click', function() {
        if (confirmModalEl) confirmModalEl.style.display = 'none';
    });

    function loadPane() {
        if (!paneUrl) return;
        fetch(paneUrl, { method: 'GET', headers: csrfHeaders() })
            .then(function(response) { return response.json(); })
            .then(function(data) {
                content.innerHTML = '';
                if (!data.success) {
                    var err = document.createElement('p');
                    err.className = 'text-muted small';
                    err.textContent = data.error || 'The accommodation pane could not be loaded.';
                    content.appendChild(err);
                    return;
                }
                var items = data.items || [];
                if (!items.length) {
                    var empty = document.createElement('p');
                    empty.className = 'text-muted small';
                    empty.textContent = 'No passengers on this booking yet.';
                    content.appendChild(empty);
                    return;
                }
                items.forEach(renderRow);
            })
            .catch(function() {
                content.innerHTML = '<p class="text-muted small">The accommodation pane could not be loaded.</p>';
            });
    }

    loadPane();
})();