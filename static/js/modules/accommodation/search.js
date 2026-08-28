// OTA AUTOCOMPLETE
(function() {
    const input = document.getElementById('destinationInput');
    const list = document.getElementById('autocompleteList');
    if (!input || !list) return;

    let timer;
    input.addEventListener('input', () => {
        clearTimeout(timer);
        timer = setTimeout(async () => {
            const q = input.value.trim();
            if (q.length < 2) { list.hidden = true; return; }
            try {
                const res = await fetch(`/accommodation/guest/api/autocomplete?q=${encodeURIComponent(q)}`);
                const data = await res.json();
                list.innerHTML = '';
                if (!data.suggestions?.length) { list.hidden = true; return; }
                data.suggestions.forEach(s => {
                    const li = document.createElement('li');
                    li.className = 'autocomplete-item';
                    li.setAttribute('role', 'option');
                    li.innerHTML = `<span>${s.icon}</span><span>${s.label}</span>${s.count ? `<span class="ac-count">${s.count} properties</span>` : ''}`;
                    li.addEventListener('click', () => {
                        input.value = s.label;
                        list.hidden = true;
                        if (s.type === 'property') window.location.href = `/accommodation/property/${s.id}`;
                    });
                    list.appendChild(li);
                });
                list.hidden = false;
            } catch(e) { list.hidden = true; }
        }, 250);
    });

    document.addEventListener('click', e => {
        if (!e.target.closest('.search-field--destination')) list.hidden = true;
    });
})();

// GUEST PICKER DROPDOWN
(function() {
    const trigger = document.getElementById('guestTrigger');
    const dropdown = document.getElementById('guestDropdown');
    if (!trigger || !dropdown) return;

    const state = {
        guests: parseInt(document.getElementById('inputGuests')?.value) || 1,
        rooms: parseInt(document.getElementById('inputRooms')?.value) || 1
    };

    const minValues = { guests: 1, rooms: 1 };
    const maxValues = { guests: 1000, rooms: 1000 };

    function updateCounter(type, delta) {
        const newValue = Math.max(minValues[type], Math.min(maxValues[type], state[type] + delta));
        state[type] = newValue;

        document.getElementById(`count${capitalize(type)}`).textContent = newValue;
        document.getElementById(`input${capitalize(type)}`).value = newValue;
        updateButtonStates();
        updateSummary();
    }

    function updateButtonStates() {
        ['guests', 'rooms'].forEach(type => {
            const decBtn = document.getElementById(`btn${capitalize(type)}Dec`);
            const incBtn = document.getElementById(`btn${capitalize(type)}Inc`);
            if (decBtn) decBtn.disabled = state[type] <= minValues[type];
            if (incBtn) incBtn.disabled = state[type] >= maxValues[type];
        });
    }

    function updateSummary() {
        let text = `${state.guests} guest${state.guests !== 1 ? 's' : ''}`;
        text += ` · ${state.rooms} room${state.rooms !== 1 ? 's' : ''}`;
        document.getElementById('guestSummary').textContent = text;
    }

    function capitalize(str) {
        return str.charAt(0).toUpperCase() + str.slice(1);
    }

    function positionDropdown() {
        const rect = trigger.getBoundingClientRect();
        dropdown.style.top = `${rect.bottom + 8}px`;
        dropdown.style.left = `${rect.left}px`;
        // Ensure dropdown doesn't go off-screen
        const dropdownRect = dropdown.getBoundingClientRect();
        if (dropdownRect.right > window.innerWidth - 16) {
            dropdown.style.left = `${window.innerWidth - dropdownRect.width - 16}px`;
        }
        if (dropdownRect.left < 16) {
            dropdown.style.left = '16px';
        }
    }

    function openDropdown() {
        dropdown.classList.add('active');
        trigger.setAttribute('aria-expanded', 'true');
        positionDropdown();
        document.addEventListener('click', handleOutsideClick);
        document.addEventListener('keydown', handleKeydown);
        window.addEventListener('scroll', positionDropdown, true);
        window.addEventListener('resize', positionDropdown);
    }

    function closeDropdown() {
        dropdown.classList.remove('active');
        trigger.setAttribute('aria-expanded', 'false');
        document.removeEventListener('click', handleOutsideClick);
        document.removeEventListener('keydown', handleKeydown);
        window.removeEventListener('scroll', positionDropdown, true);
        window.removeEventListener('resize', positionDropdown);
    }

    function handleOutsideClick(e) {
        if (!trigger.contains(e.target) && !dropdown.contains(e.target)) {
            closeDropdown();
        }
    }

    function handleKeydown(e) {
        if (e.key === 'Escape') {
            closeDropdown();
            trigger.focus();
        }
        if (e.key === 'Tab' && dropdown.classList.contains('active')) {
            const focusableElements = dropdown.querySelectorAll('button:not(:disabled)');
            const firstElement = focusableElements[0];
            const lastElement = focusableElements[focusableElements.length - 1];
            if (e.shiftKey && document.activeElement === firstElement) {
                e.preventDefault();
                lastElement.focus();
            } else if (!e.shiftKey && document.activeElement === lastElement) {
                e.preventDefault();
                firstElement.focus();
            }
        }
    }

    trigger.addEventListener('click', (e) => {
        e.stopPropagation();
        if (dropdown.classList.contains('active')) {
            closeDropdown();
        } else {
            openDropdown();
        }
    });

    trigger.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            if (dropdown.classList.contains('active')) {
                closeDropdown();
            } else {
                openDropdown();
            }
        }
    });

    document.getElementById('btnDone').addEventListener('click', closeDropdown);

    ['guests', 'rooms'].forEach(type => {
        document.getElementById(`btn${capitalize(type)}Inc`).addEventListener('click', () => updateCounter(type, 1));
        document.getElementById(`btn${capitalize(type)}Dec`).addEventListener('click', () => updateCounter(type, -1));
    });

    // Initialize button states
    ['guests', 'rooms'].forEach(type => updateButtonStates());
})();

// WISHLIST TOGGLE
function toggleSave(e, propertyId) {
    e.preventDefault(); e.stopPropagation();
    const btn = e.currentTarget;
    const saved = btn.getAttribute('data-saved') === 'true';
    btn.setAttribute('data-saved', !saved);
    // Persist to backend if user is logged in
    fetch(`/accommodation/api/wishlist/${propertyId}`, {
        method: saved ? 'DELETE' : 'POST',
        headers: { 'X-CSRFToken': document.querySelector('[name=csrf_token]')?.value || '' }
    }).catch(() => {});
}