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