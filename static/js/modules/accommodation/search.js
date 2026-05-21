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
                const res = await fetch(`/accommodation/api/autocomplete?q=${encodeURIComponent(q)}`);
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