/* Event host guest coordination UI.  The server remains authoritative for all checks. */
(function () {
    'use strict';

    const root = document.getElementById('guestCoordination');
    if (!root) return;

    let accommodationRegistrationRef = null;
    let transportRegistrationRef = null;
    const csrf = document.getElementById('csrfToken')?.value || '';

    const result = (id, message, ok) => {
        const element = document.getElementById(id);
        if (!element) return;
        element.textContent = message;
        element.className = `alert ${ok ? 'alert-success' : 'alert-danger'}`;
        element.hidden = false;
    };

    const setLoading = (id, value) => {
        const element = document.getElementById(id);
        if (element) element.hidden = !value;
    };

    async function getJson(url) {
        const response = await fetch(url, {headers: {'Accept': 'application/json'}});
        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.error || data.message || 'The coordination service is unavailable.');
        }
        return data;
    }

    async function loadAccommodationBookings() {
        const select = document.getElementById('propertySelect');
        if (!select) return;
        select.replaceChildren(new Option('Loading reserved bookings...', ''));
        select.disabled = true;
        try {
            const data = await getJson(root.dataset.propertiesUrl);
            select.replaceChildren(new Option('-- Select reserved accommodation --', ''));
            data.properties.forEach((booking) => {
                const dates = booking.check_in && booking.check_out
                    ? ` (${booking.check_in} to ${booking.check_out})` : '';
                select.add(new Option(
                    `${booking.title} — ${booking.remaining_capacity} guest place(s)${dates}`,
                    booking.booking_ref
                ));
            });
            select.disabled = data.properties.length === 0;
            if (!data.properties.length) select.replaceChildren(new Option('No reserved accommodation available', ''));
        } catch (error) {
            select.replaceChildren(new Option(error.message, ''));
        }
    }

    async function loadTransportBookings() {
        const select = document.getElementById('transportBookingSelect');
        if (!select) return;
        select.replaceChildren(new Option('Loading reserved transport...', ''));
        select.disabled = true;
        try {
            const data = await getJson(root.dataset.driversUrl);
            select.replaceChildren(new Option('-- Select reserved transport --', ''));
            data.drivers.forEach((booking) => {
                select.add(new Option(
                    `${booking.vehicle} — ${booking.pickup_time || 'scheduled'}`,
                    booking.booking_ref
                ));
            });
            select.disabled = data.drivers.length === 0;
            if (!data.drivers.length) select.replaceChildren(new Option('No eligible transport available', ''));
        } catch (error) {
            select.replaceChildren(new Option(error.message, ''));
        }
    }

    async function postAssignment(url, registrationRef, bookingRef, resultId, loadingId) {
        if (!registrationRef || !bookingRef) throw new Error('Select a reserved resource first.');
        setLoading(loadingId, true);
        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'Accept': 'application/json', 'X-CSRFToken': csrf},
                body: JSON.stringify({registration_ref: registrationRef, booking_ref: bookingRef})
            });
            const data = await response.json();
            if (!response.ok || !data.success) throw new Error(data.error || 'Assignment failed.');
            result(resultId, 'Assignment completed.', true);
            window.setTimeout(() => window.location.reload(), 700);
        } catch (error) {
            result(resultId, error.message, false);
        } finally {
            setLoading(loadingId, false);
        }
    }

    document.querySelectorAll('.assign-accommodation-btn').forEach((button) => {
        button.addEventListener('click', () => {
            accommodationRegistrationRef = button.dataset.registrationRef;
            document.getElementById('accommodationAttendeeName').value = button.dataset.name || '';
            document.getElementById('accommodationResult').hidden = true;
            loadAccommodationBookings();
        });
    });

    document.querySelectorAll('.assign-transport-btn').forEach((button) => {
        button.addEventListener('click', () => {
            transportRegistrationRef = button.dataset.registrationRef;
            document.getElementById('transportAttendeeName').value = button.dataset.name || '';
            document.getElementById('transportResult').hidden = true;
            loadTransportBookings();
        });
    });

    document.getElementById('confirmAccommodationBtn')?.addEventListener('click', () => {
        postAssignment(
            root.dataset.accommodationUrl,
            accommodationRegistrationRef,
            document.getElementById('propertySelect')?.value,
            'accommodationResult',
            'accommodationLoading'
        );
    });

    document.getElementById('confirmTransportBtn')?.addEventListener('click', () => {
        postAssignment(
            root.dataset.transportUrl,
            transportRegistrationRef,
            document.getElementById('transportBookingSelect')?.value,
            'transportResult',
            'transportLoading'
        );
    });

    document.querySelectorAll('.cancel-coordination-btn').forEach((button) => {
        button.addEventListener('click', async () => {
            const registrationRef = button.dataset.registrationRef;
            const capability = button.dataset.capability;
            if (!window.confirm(`Cancel ${capability} for this attendee?`)) return;
            try {
                const response = await fetch(
                    `${root.dataset.coordinationUrl}/${encodeURIComponent(registrationRef)}/${capability}`,
                    {method: 'DELETE', headers: {'Accept': 'application/json', 'X-CSRFToken': csrf}}
                );
                const data = await response.json();
                if (!response.ok || !data.success) throw new Error(data.error || 'Cancellation failed.');
                window.location.reload();
            } catch (error) {
                window.alert(error.message);
            }
        });
    });
}());