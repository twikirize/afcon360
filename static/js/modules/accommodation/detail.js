// Sticky bar: show when booking form scrolls out of view
(function() {
    const bar = document.getElementById('stickyBar');
    const form = document.getElementById('booking-form') ||
                 document.querySelector('.booking-widget') ||
                 document.querySelector('form[action*="book"]');
    if (!bar || !form) return;
    const obs = new IntersectionObserver(([e]) => {
        bar.style.display = e.isIntersecting ? 'none' : 'flex';
    }, { threshold: 0.1 });
    obs.observe(form);
})();

function smoothToBooking(e) {
    e.preventDefault();
    const form = document.getElementById('booking-form') ||
                 document.querySelector('.booking-widget');
    form?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
function openAllPhotos() {
    const modal = document.getElementById('photoModal');
    if (!modal) return;
    modal.hidden = false;
    modal.classList.add('is-open');
    document.body.classList.add('photo-modal-open');
    modal.querySelector('.photo-modal-close')?.focus();
}

let photoViewerIndex = 0;
let photoViewerTrigger = null;

function photoViewerItems() {
    return Array.from(document.querySelectorAll('#photoModalImages .photo-modal-image'));
}

function openPhotoViewer(index) {
    const items = photoViewerItems();
    const viewer = document.getElementById('photoLightbox');
    const image = document.getElementById('photoLightboxImage');
    if (!viewer || !image || !items.length) return;
    photoViewerIndex = (index + items.length) % items.length;
    const item = items[photoViewerIndex];
    image.src = item.dataset.photo;
    image.alt = item.querySelector('img')?.alt || `Property photo ${photoViewerIndex + 1}`;
    const counter = document.getElementById('photoLightboxCounter');
    if (counter) counter.textContent = `${photoViewerIndex + 1} of ${items.length}`;
    viewer.hidden = false;
    viewer.classList.add('is-open');
    document.getElementById('photoLightboxImage')?.focus();
}

function closePhotoViewer() {
    const viewer = document.getElementById('photoLightbox');
    if (!viewer) return;
    viewer.hidden = true;
    viewer.classList.remove('is-open');
    photoViewerTrigger?.focus();
    photoViewerTrigger = null;
}

function movePhoto(step) {
    openPhotoViewer(photoViewerIndex + step);
}

document.addEventListener('DOMContentLoaded', function() {
    const modal = document.getElementById('photoModal');
    if (!modal) return;

    modal.querySelectorAll('[data-photo-modal-close]').forEach(function(control) {
        control.addEventListener('click', closeAllPhotos);
    });
    modal.querySelectorAll('.photo-modal-image').forEach(function(photo, index) {
        photo.addEventListener('click', function() {
            photoViewerTrigger = photo;
            openPhotoViewer(index);
        });
    });
    modal.querySelector('[data-photo-lightbox-close]')?.addEventListener('click', closePhotoViewer);
    modal.querySelectorAll('[data-photo-lightbox-prev]').forEach(control => control.addEventListener('click', () => movePhoto(-1)));
    modal.querySelectorAll('[data-photo-lightbox-next]').forEach(control => control.addEventListener('click', () => movePhoto(1)));
    let touchStartX = null;
    const lightboxImage = document.getElementById('photoLightboxImage');
    lightboxImage?.addEventListener('touchstart', event => { touchStartX = event.changedTouches[0].clientX; }, { passive: true });
    lightboxImage?.addEventListener('touchend', event => {
        if (touchStartX === null) return;
        const distance = event.changedTouches[0].clientX - touchStartX;
        if (Math.abs(distance) > 40) movePhoto(distance < 0 ? 1 : -1);
        touchStartX = null;
    }, { passive: true });
    document.addEventListener('keydown', function(event) {
        const viewer = document.getElementById('photoLightbox');
        if (viewer && !viewer.hidden) {
            if (event.key === 'Escape') closePhotoViewer();
            if (event.key === 'ArrowLeft') movePhoto(-1);
            if (event.key === 'ArrowRight') movePhoto(1);
            return;
        }
        if (event.key === 'Escape' && !modal.hidden) closeAllPhotos();
    });
});

function closeAllPhotos() {
    const modal = document.getElementById('photoModal');
    if (!modal) return;
    modal.hidden = true;
    modal.classList.remove('is-open');
    document.body.classList.remove('photo-modal-open');
}

(function() {
    function onReady(callback) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', callback, { once: true });
        } else {
            callback();
        }
    }

    onReady(function() {
        const availabilityForm = document.getElementById('availability-form');
        const checkInInput = document.getElementById('check_in');
        const checkOutInput = document.getElementById('check_out');
        const dateRangeFeedback = document.getElementById('date_range_feedback');
        const dateRangeMessage = document.getElementById('date_range_message');
        const roomTypeIdInput = document.getElementById('room_type_id');
        const liveResults = document.getElementById('live_availability_results');
        const liveContent = document.getElementById('live_availability_content');
        const checkButton = availabilityForm?.querySelector('button[type="submit"]');
        const propertyId = availabilityForm?.dataset.propertyId;
        const today = new Date();
        const todayStr = today.toLocaleDateString('en-CA');

        function formatDate(value) {
            const d = new Date(`${value}T00:00:00`);
            return d.toLocaleDateString('en-CA');
        }

        function addDays(value, days) {
            const result = new Date(`${value}T00:00:00`);
            result.setDate(result.getDate() + days);
            return formatDate(result);
        }

        function showDateFeedback(message, type) {
            if (!dateRangeFeedback || !dateRangeMessage) return;
            dateRangeMessage.textContent = message;
            dateRangeFeedback.className = `alert alert-${type}`;
            dateRangeFeedback.style.display = 'block';
            dateRangeFeedback.classList.add('mt-2');
        }

        function hideDateFeedback() {
            if (dateRangeFeedback) dateRangeFeedback.style.display = 'none';
        }

        function validateCheckIn() {
            if (!checkInInput) return true;
            const value = checkInInput.value;
            if (!value) {
                if (checkOutInput) {
                    checkOutInput.value = '';
                    checkOutInput.min = '';
                    checkOutInput.disabled = true;
                }
                checkInInput.max = '';
                hideDateFeedback();
                return true;
            }
            if (value < todayStr) {
                showDateFeedback('Check-in date cannot be in the past. Please select a future date.', 'danger');
                checkInInput.classList.add('is-invalid');
                return false;
            }
            checkInInput.classList.remove('is-invalid');

            if (checkOutInput) {
                const minimumCheckout = addDays(value, 1);
                checkOutInput.min = minimumCheckout;
                checkOutInput.disabled = false;
                if (checkOutInput.value && checkOutInput.value < minimumCheckout) {
                    checkOutInput.value = '';
                }
                checkInInput.max = checkOutInput.value ? addDays(checkOutInput.value, -1) : '';
            }

            hideDateFeedback();
            return true;
        }

        function validateCheckOut() {
            if (!checkOutInput) return true;
            const value = checkOutInput.value;
            const checkInValue = checkInInput?.value || '';
            if (!checkInValue) {
                checkOutInput.value = '';
                checkOutInput.disabled = true;
                showDateFeedback('Select a check-in date first.', 'warning');
                checkOutInput.classList.add('is-invalid');
                return false;
            }
            if (!value) {
                checkInInput.max = '';
                hideDateFeedback();
                return true;
            }
            if (value <= checkInValue) {
                showDateFeedback('Check-out must be after check-in date.', 'danger');
                checkOutInput.classList.add('is-invalid');
                return false;
            }
            if (value < todayStr) {
                showDateFeedback('Check-out date cannot be in the past.', 'danger');
                checkOutInput.classList.add('is-invalid');
                return false;
            }
            checkInInput.max = addDays(value, -1);
            checkOutInput.classList.remove('is-invalid');
            hideDateFeedback();
            return true;
        }

        function renderAvailabilityResults(data) {
            if (!liveContent) return;
            let html = '';
            const roomTypes = data.room_types || [];

            if (data.tier0_exact_match?.length) {
                html += '<div class="alert alert-success mb-0"><i class="fas fa-check-circle"></i> <strong>Available!</strong> ';
                data.tier0_exact_match.forEach((roomType, index) => {
                    html += `${roomType.name} (${roomType.available_units} rooms available)`;
                    if (index < data.tier0_exact_match.length - 1) html += ', ';
                });
                html += '</div>';
            } else if (data.tier1_same_property?.length) {
                html += '<div class="alert alert-info mb-0"><i class="fas fa-info-circle"></i> <strong>Partial match:</strong> Your selected room type is limited, but similar options are available at this property.</div>';
                data.tier1_same_property.forEach(roomType => {
                    html += `<div class="small mt-1"><i class="fas fa-door-open"></i> ${roomType.name} — ${roomType.available_units} rooms, up to ${roomType.max_guests} guests, $${roomType.price}/night</div>`;
                });
            } else if (data.tier2_nearby_properties?.length) {
                html += '<div class="alert alert-warning mb-0"><i class="fas fa-map-marker-alt"></i> <strong>No rooms at this property.</strong> Nearby alternatives:</div>';
                data.tier2_nearby_properties.forEach(property => {
                    html += `<div class="small mt-1"><i class="fas fa-building"></i> ${property.name} — ${property.distance_km}km away, ${property.room_type.name} available</div>`;
                });
            } else {
                const message = data.partial_availability?.message || 'No rooms available for your dates.';
                html += `<div class="alert alert-danger mb-0"><i class="fas fa-times-circle"></i> <strong>Not available:</strong> ${message}</div>`;
            }

            if (roomTypes.length) {
                html += '<div class="small text-muted mt-2">';
                roomTypes.forEach(roomType => {
                    if (roomType.available_units > 0) {
                        html += `<i class="fas fa-check text-success"></i> ${roomType.name}: ${roomType.available_units} rooms — `;
                    } else if (roomType.status === 'partial') {
                        html += `<i class="fas fa-clock text-warning"></i> ${roomType.name}: ${roomType.blocked_dates.length} date(s) blocked — `;
                    } else {
                        html += `<i class="fas fa-times text-danger"></i> ${roomType.name}: sold out — `;
                    }
                });
                html += '</div>';
            }

            liveContent.innerHTML = html;

            if (checkButton) {
                const isAvailable = !!data.tier0_exact_match?.length;
                checkButton.disabled = !isAvailable;
                checkButton.title = checkButton.disabled ? 'Select different dates to check availability' : '';
                checkButton.textContent = isAvailable ? 'Continue to Checkout' : 'Check Availability';
            }
        }

        function redirectToCheckout() {
            const checkIn = checkInInput?.value || '';
            const checkOut = checkOutInput?.value || '';
            const guests = document.querySelector('input[name="guests"]')?.value || '2';
            const roomTypeId = roomTypeIdInput?.value || '';
            if (!propertyId || !checkIn || !checkOut) return;
            const params = new URLSearchParams({
                property_id: propertyId,
                check_in: checkIn,
                check_out: checkOut,
                num_guests: guests,
            });
            if (roomTypeId) params.append('room_type_id', roomTypeId);
            window.location.href = `/accommodation/guest/checkout?${params.toString()}`;
        }

        function checkLiveAvailability() {
            const checkIn = checkInInput?.value || '';
            const checkOut = checkOutInput?.value || '';
            const guests = document.querySelector('input[name="guests"]')?.value || '2';
            if (!propertyId || !checkIn || !checkOut || checkIn >= checkOut) return;

            if (liveResults) liveResults.style.display = 'block';
            if (liveContent) liveContent.innerHTML = '<div class="text-center py-3"><i class="fas fa-spinner fa-spin"></i> Checking availability...</div>';

            const params = new URLSearchParams({
                property_id: propertyId,
                check_in: checkIn,
                check_out: checkOut,
                num_guests: guests,
                num_rooms: '1'
            });
            fetch(`/accommodation/api/availability?${params.toString()}`, {
                headers: { Accept: 'application/json' }
            })
                .then(response => response.json().then(data => ({ ok: response.ok, data })))
                .then(({ ok, data }) => {
                    if (ok) {
                        renderAvailabilityResults(data);
                    } else if (liveContent) {
                        liveContent.innerHTML = `<div class="alert alert-warning mb-0"><i class="fas fa-exclamation-triangle"></i> ${data.error || 'Unable to check availability'}</div>`;
                    }
                })
                .catch(() => {
                    if (liveContent) liveContent.innerHTML = '<div class="alert alert-warning mb-0"><i class="fas fa-exclamation-triangle"></i> Unable to check availability</div>';
                });
        }

        function selectRoomType(roomTypeId) {
            if (!roomTypeIdInput) return;
            roomTypeIdInput.value = roomTypeId;
            document.querySelectorAll('.room-type-card').forEach(card => card.classList.remove('border-primary', 'border-3'));
            document.querySelectorAll('[data-select-room]').forEach(button => {
                const selected = button.dataset.selectRoom === String(roomTypeId);
                button.className = `btn ${selected ? 'btn-primary' : 'btn-outline-primary'} btn-sm w-100`;
                button.innerHTML = selected ? '<i class="fas fa-check"></i> Selected' : 'Select Room';
                if (selected) button.closest('.room-type-card')?.classList.add('border-primary', 'border-3');
            });
        }

        document.querySelectorAll('[data-select-room]').forEach(button => {
            button.addEventListener('click', () => selectRoomType(button.dataset.selectRoom));
        });
        document.querySelectorAll('[data-open-photos]').forEach(button => button.addEventListener('click', openAllPhotos));
        document.querySelectorAll('[data-gallery-image]').forEach(image => {
            image.addEventListener('click', () => {
                const hero = document.getElementById('galleryHero');
                if (hero) hero.src = image.dataset.galleryImage;
            });
        });
        document.querySelectorAll('[data-smooth-booking]').forEach(link => {
            link.addEventListener('click', event => {
                event.preventDefault();
                document.getElementById('availability-form')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
            });
        });

        checkInInput?.addEventListener('change', () => {
            validateCheckIn();
            if (checkInInput.value && checkOutInput?.value) checkLiveAvailability();
        });
        checkInInput?.addEventListener('input', () => {
            validateCheckIn();
            if (checkInInput.value && checkOutInput?.value && checkOutInput.value > checkInInput.value) checkLiveAvailability();
        });
        checkInInput?.addEventListener('blur', validateCheckIn);
        checkInInput?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') e.preventDefault();
        });
        checkOutInput?.addEventListener('change', () => {
            validateCheckOut();
            if (checkInInput?.value && checkOutInput.value) checkLiveAvailability();
        });
        checkOutInput?.addEventListener('input', () => {
            validateCheckOut();
            if (checkInInput?.value && checkOutInput.value > checkInInput.value) checkLiveAvailability();
        });
        checkOutInput?.addEventListener('blur', validateCheckOut);
        checkOutInput?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') e.preventDefault();
        });
        document.querySelector('input[name="guests"]')?.addEventListener('change', checkLiveAvailability);

        availabilityForm?.addEventListener('submit', event => {
            event.preventDefault();
            if (!validateCheckIn() || !validateCheckOut()) return;
            redirectToCheckout();
        });

        checkButton?.addEventListener('click', (e) => {
            e.preventDefault();
            if (!checkButton.disabled) redirectToCheckout();
        });

        if (checkInInput) {
            checkInInput.min = todayStr;
            if (checkInInput?.value) {
                validateCheckIn();
            } else if (checkOutInput) {
                checkOutInput.disabled = true;
            }
        }
        if (checkInInput?.value && checkOutInput?.value) setTimeout(checkLiveAvailability, 500);
    });
})();