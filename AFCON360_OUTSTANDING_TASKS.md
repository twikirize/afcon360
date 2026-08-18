# AFCON360 Booking Workstream — Outstanding Items Task List
**For:** implementing agent, executed one task at a time, in order
**Rule for every task below:** VERIFY the stated location/problem still matches the current codebase before writing anything. Code shown here is not to be pasted blind — confirm the surrounding file first, since several tasks depend on files that were not directly inspected during design. IMPLEMENT the smallest change that closes the gap. REFACTOR only what the task touches — do not "improve" adjacent code. Stop after each task and confirm before moving to the next.

## Triage order

| Order | Tasks | Priority | Why |
|---|---|---|---|
| Do next | 11, 10, 1 | High | Correct the booking API contract first, then complete the deferred third-party guest-details flow end to end. |
| Do next | 7, 8, 12 | High | Make guest registration reachable, editable, and verifiably safe through both roster and public-link paths. |
| Do next | 3, 6 | High | Repair the event accommodation integration and expose already-built delegation capability. |
| Do next | 2, 13, 14, 15 | Medium | Complete checkout payment/request presentation only after the backend currency and policy sources are verified. |
| Schedule | 5, 17, 18 | Medium | Add scheduled nudging and validate concurrency/database migration state in a controlled environment. |
| Design review | 4 | High | Room-aware holds affect availability correctness and must be designed from the live implementation before coding. |
| Closed decision | 9, 20 | — | i18n remains out of scope; `replace()` keeps independently committed remove/create operations. |

### Required execution contract

For every actionable task, the implementing agent must:

1. **Verify** the stated file, route, model, service, call sites, and current behavior against the live repository.
2. **Write a failing regression test or reproducible check first** for a bug or behavior change, unless the task is documentation-only or the environment blocks execution; record that limitation.
3. **Implement** the smallest change that closes the verified gap, preserving module guards, CSRF, dual-ID rules, idempotency, and existing service boundaries.
4. **Refactor** only touched code where needed for the fix; do not perform unrelated cleanup.
5. **Run verification** appropriate to the task, including the affected tests and import/startup checks. Never run migrations or production database changes automatically.
6. **Report** files changed, behavior fixed, tests/checks run, migration commands proposed (if any), manual steps, risks, and unresolved discrepancies.

If verification contradicts this inventory, stop that task and update its status with the observed reality instead of forcing the proposed solution to fit.

---

## Decisions made on the two open questions before this list

**Item 19 (notification on guest removal):** Not automatic, not a separate opt-in setting. The booker is prompted **at the moment of removal**, every time, with a simple choice: *"Notify [name] that they've been removed from this booking?"* — Yes/No, decided per-removal, not configured once. This covers the case correctly: some removed entries were never real registered guests to begin with (a booker-added placeholder, or a name the booker typed and never actually shared with anyone) — for those, "notify" would be meaningless, so the prompt only fires when the row being removed has a real contact channel (`guest_email` or `guest_phone` populated) and `registration_source == 'self'` (i.e. they registered themselves, so they plausibly know they were on this booking). Placeholder/host-added rows with no contact info skip the prompt entirely — nothing to notify.

**Item 20 (replace() atomicity):** Decided: **keep `remove()` and `create()` as two independently-committed operations, not one transaction.** Reasoning: a removal is a completed, durable decision the moment the booker confirms it — it must never be silently undone just because the replacement's details turned out incomplete or invalid. Wrapping both in one transaction would mean a typo in the new guest's name rolls back a removal the booker already confirmed, which is the wrong failure mode. If `create()` fails after `remove()` succeeds, the correct and current behavior is: the seat is now open, the roster shows one fewer active guest, and the booker (or anyone via the shared link) can fill it in a separate action — same as any other open seat. No code change needed for this item; it is already built this way. This entry exists so the reasoning is on record, not because there's a fix pending.

---

## Task 1 — `defer_guest_details` toggle missing from checkout

**Problem, where found:** `templates/accommodation/guest/checkout.html`, `thirdPartySection` (around the `primary_guest_name`/`primary_guest_email` inputs). Fields are hard-required with no way to defer. `checkout.js` has no corresponding logic either — confirmed absent in both files.

**Solution:**
```html
<!-- Inside #thirdPartySection, above the name/email inputs -->
<div class="form-check form-switch mb-3">
  <input class="form-check-input" type="checkbox" id="deferGuestToggle">
  <label class="form-check-label" for="deferGuestToggle">
    I don't have their details right now — send them a link to fill it in themselves
  </label>
</div>
<input type="hidden" name="defer_guest_details" id="deferGuestDetailsInput" value="0">
```
```javascript
// checkout.js
document.getElementById('deferGuestToggle')?.addEventListener('change', function () {
    var on = this.checked;
    document.getElementById('deferGuestDetailsInput').value = on ? '1' : '0';
    document.querySelectorAll('#thirdPartyFields input').forEach(function (el) {
        el.required = !on;
    });
    document.getElementById('thirdPartyFields')?.classList.toggle('d-none', on);
});
```

**Agent actions:**
1. Verify — confirm `thirdPartySection`'s current markup and confirm `checkout.js` still has no defer logic.
2. Implement — add the markup and JS above.
3. Verify the checkout POST route (Task 10) actually reads `defer_guest_details` before this toggle does anything meaningful — if Task 10 isn't done yet, this toggle will submit but be ignored server-side. Flag that dependency in your completion note rather than silently shipping a toggle that does nothing.

---

## Task 2 — FX conversion note not shown in Step 3

**Problem, where found:** `checkout.js`, `selectPaymentMethod()`. Updates `.summary-currency` label text but never computes or displays a converted amount when the method's currency differs from the guest's own wallet/session currency.

**Solution:**
```javascript
// Requires the page to expose the guest's session currency, e.g. via a
// data attribute on the form: <form ... data-session-currency="UGX">
function updateFxNote(methodCurrency) {
    var sessionCurrency = document.getElementById('checkout-form')?.dataset.sessionCurrency;
    var fxNote = document.getElementById('fxNote');
    if (!fxNote) return;
    if (!sessionCurrency || sessionCurrency === methodCurrency) {
        fxNote.textContent = '';
        return;
    }
    // Requires a rate lookup — do not hardcode a rate. Call the existing
    // FX endpoint (verify the real path before wiring this in; not
    // confirmed in this thread) and render:
    // fxNote.textContent = `≈ ${sessionCurrency} ${converted} at today's rate`;
}
```

**Agent actions:**
1. Verify — find the real FX rate lookup endpoint/service already in the wallet module (referenced throughout this thread as "your FX system" but never inspected directly). Do not invent a rate source.
2. Implement — call it from `selectPaymentMethod()`, populate a `#fxNote` element (already present in the checkout.html markup from earlier in this thread — confirm it's still there).
3. If no such endpoint exists yet, stop and report back rather than fabricating one — this is a real backend dependency, not a front-end-only fix.

---

## Task 3 — `assign_accommodation()` broken call to `create_booking()`

**Problem, where found:** `app/events/routes/assignment.py`, function `assign_accommodation()`. Calls `BookingService.create_booking(check_in_date=..., check_out_date=...)` and omits `guest_name`/`guest_email` entirely — signature mismatch confirmed against the real `create_booking()` definition.

**Solution:**
```python
# Correct the call to match the real signature (verify current signature
# after Task 11 lands, since guest_name/guest_email become optional there):
booking, error = BookingService.create_booking(
    guest_user_id=registration.user_id,
    property_id=property_id,
    check_in=datetime.fromisoformat(check_in).date(),
    check_out=datetime.fromisoformat(check_out).date(),
    guest_name=registration.full_name,
    guest_email=registration.email,
    context_type='EVENT',
    context_id=str(event_id),
)
```

**Agent actions:**
1. Verify — confirm this function is actually reachable/used before spending time here (check for any route tests or logs referencing `/events/<id>/accommodation/assign`).
2. Implement the corrected call once `create_booking()`'s real current signature is confirmed (do this task after Task 11, not before).
3. Add a regression test that actually calls this route — the report earlier in this workstream self-admitted this path was never verified to run.

---

## Task 4 — `RoomHold` never instantiated, `create_hold()` writes to `BlockedDate`

**Problem, where found:** accommodation availability service, function `create_hold()` (exact file not directly inspected in this thread — locate via `grep -rn "def create_hold"`). Writes to the property-wide `BlockedDate` table; the unit-aware `RoomHold` model exists and is exported but never instantiated anywhere in the codebase.

**Solution:** Not written here — this is a real availability-engine change, not a small patch, and needs its own design pass with the actual `create_hold()` body in hand.

**Agent actions:**
1. Verify — locate `create_hold()`, paste its current body.
2. Stop and report back rather than implementing blind. This task is a placeholder for a follow-up design session, not something to execute mechanically.

---

## Task 5 — No pre-arrival re-prompt for special requests

**Problem, where found:** Nowhere yet — this touchpoint (a reminder a few days before check-in, distinct from the immediate post-confirmation prompt already built into `confirmation.html`) was designed in Addendum 1 §2 but never implemented as a scheduled job or notification.

**Solution:**
```python
# New scheduled task, likely alongside existing Celery/cron jobs in the
# accommodation module (locate the existing job scheduler pattern first —
# do not invent a new one).
def send_pre_arrival_request_reminder():
    """Runs daily. Nudges bookings 3 days out with no special request yet."""
    target_date = date.today() + timedelta(days=3)
    bookings = AccommodationBooking.query.filter(
        AccommodationBooking.check_in == target_date,
        AccommodationBooking.status == AccommodationBookingStatus.CONFIRMED.value,
    ).all()
    for booking in bookings:
        if not SpecialRequestService.get_for_booking(booking.id):
            # send via existing NotificationService — verify its real call
            # signature before wiring this in.
            pass
```

**Agent actions:**
1. Verify — find the existing scheduled-job mechanism (Celery beat config, cron entry, or similar — referenced in this thread's history as already present for other periodic tasks).
2. Implement using that same mechanism, not a new one.
3. Confirm it only fires once per booking (idempotency — don't re-notify daily for the same booking).

---

## Task 6 — No delegation UI in `guest_roster.html`

**Problem, where found:** `templates/accommodation/guest/guest_roster.html`. Backend (`Delegation` model, `DelegationService`, `RegistrationPermissionService`) is real and DB-backed as of this workstream's last round, but there is no button, form, or entry point anywhere on this page to actually grant delegated access.

**Solution:**
```html
<!-- Add near the top of guest_roster.html, visible only to the booker/owner -->
{% if can_manage %}
<div class="card shadow-sm mb-4">
  <div class="card-body">
    <h2 class="h6">Delegate roster management</h2>
    <p class="small text-muted">Let someone else (an assistant, HR staff) manage this guest list on your behalf.</p>
    <form method="post" action="{{ url_for('accommodation.delegate_registration', booking_id=booking.id) }}" class="row g-2">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
      <div class="col-8"><input type="email" name="delegatee_email" class="form-control" placeholder="Their email" required></div>
      <div class="col-4"><button class="btn btn-outline-primary w-100" type="submit">Delegate</button></div>
    </form>
  </div>
</div>
{% endif %}
```
Corresponding route needed (verify a similar pattern already exists for other delegation types before writing this from scratch):
```python
@accommodation_bp.route('/booking/<int:booking_id>/delegate', methods=['POST'])
@login_required
def delegate_registration(booking_id):
    booking = AccommodationBooking.query.get_or_404(booking_id)
    if current_user.id not in (booking.booked_by_user_id, booking.booking_owner_id):
        abort(403)
    delegatee = User.query.filter_by(email=request.form['delegatee_email']).first_or_404()
    from app.auth.delegation import DelegationService, DelegationScope
    result = DelegationService().create_delegation(
        delegator_id=current_user.id, delegatee_id=delegatee.id,
        delegator_role='user', delegatee_role='user',
        scopes=[DelegationScope.ACCOMMODATION_REGISTRATION_MANAGEMENT],
        duration_hours=168, reason=f"Roster management for booking {booking.booking_reference}",
    )
    flash('Delegated' if result['success'] else result['error'])
    return redirect(url_for('accommodation.guest_roster', booking_id=booking_id))
```

**Agent actions:**
1. Verify `can_manage` context variable exists on this template's render call, or add it via `RegistrationPermissionService.can_manage_registrations()`.
2. Implement the form + route.
3. Test: delegate to a second test user, confirm that user can now see/act on the roster.

---

## Task 7 — No manual single-guest add form on the roster page

**Problem, where found:** `templates/accommodation/guest/guest_roster.html` — only bulk upload and Remove exist. `confirmation.html` links to `accommodation.guest_register`, but that route/template was never inspected in this thread — may already solve this elsewhere.

**Agent actions:**
1. Verify first — check whether `accommodation.guest_register` already provides single-guest add. If yes, this task is done; just confirm the roster page links to it (it appears to, per `confirmation.html`).
2. If no such route/template exists, build a small form using `GuestRosterEntryForm` (already defined in `booking_forms.py`) posting to a new `add_registration` route calling `RegistrationService.create(..., source='host')`.

---

## Task 8 — No "Edit" action for placeholder seats

**Problem, where found:** `guest_roster.html` table — only a Remove button per row; placeholders (`is_placeholder=True`) have no inline edit path.

**Solution:**
```html
{% if registration.is_active and registration.is_placeholder %}
<a class="btn btn-sm btn-outline-primary"
   href="{{ url_for('accommodation.edit_registration', booking_id=booking.id, registration_id=registration.id) }}">Edit</a>
{% endif %}
```
Route: a simple form pre-filled with the placeholder's current (likely empty) fields, posting to `RegistrationService` — do not build a new service method; this is just `create()`-shaped data applied via an UPDATE on the existing row rather than remove+create, since a placeholder being filled in for the first time isn't a "replacement," it's completion.

**Agent actions:**
1. Verify no such edit path exists elsewhere already.
2. Implement the route + minimal template, reusing `GuestRosterEntryForm`.
3. On submit, update the existing row's fields directly (not `RegistrationService.replace()` — that's for swapping a named occupant, not completing a placeholder) and flip `is_placeholder` to `False` once a real name is saved.

---

## Task 9 — i18n / translation layer

**Status:** Out of scope for this workstream by design (stated explicitly in the base spec). Not a task to execute — listed here only so it isn't mistaken for forgotten.

---

## Task 10 — Checkout POST route: drop third-party required-fields gate, wire `defer_guest_details`

**Problem, where found:** `app/accommodation/routes.py`, the checkout POST handler (`required_fields` check around `booking_type == 'third_party'`, confirmed in this thread's earlier diagnosis, exact current line numbers not re-verified since).

**Solution:**
```python
# Remove primary_guest_name / primary_guest_email from required_fields
# for booking_type == 'third_party'. Replace with:
if booking_type == 'third_party' and request.form.get('defer_guest_details') == '1':
    # Do not require name/email. Generate a claim token instead.
    import secrets, hashlib
    raw_token = secrets.token_urlsafe(32)
    booking.claim_token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    booking.owner_email = None  # unknown yet
    # Send raw_token via whatever share mechanism the confirmation page uses
    # (verify — this may already reuse BookingRegistrationLink's pattern
    # rather than claim_token_hash; check confirmation.html's actual
    # registration_url source before assuming which mechanism applies here)
```

**Agent actions:**
1. Verify current `required_fields` block against the live file — this was last directly inspected several rounds ago in this thread and may have already changed.
2. Implement the conditional bypass.
3. This task and Task 1 are two halves of the same feature — do not consider either done without the other; test the full path (toggle checked at checkout → booking created with no guest name → claim/registration link actually sent).

---

## Task 11 — `create_booking()` signature: make `guest_name`/`guest_email` optional, flip precedence

**Problem, where found:** `app/accommodation/services/booking_service.py`, `create_booking()`. Declared as required positional params with no default; internal fallback logic treats legacy fields as primary and `primary_guest_*` as fallback — backwards from intended design.

**Solution:**
```python
def create_booking(
    self,
    guest_user_id,
    property_id,
    check_in,
    check_out,
    guest_name: str = None,      # was required, no default
    guest_email: str = None,     # was required, no default
    guest_phone: str = None,
    primary_guest_name: str = None,
    primary_guest_email: str = None,
    ...
):
    ...
    # Flip precedence — primary_guest_* becomes canonical, legacy is the mirror
    guest_name_to_store = primary_guest_name or guest_name
    guest_email_to_store = primary_guest_email or guest_email
    ...
    booking = AccommodationBooking(
        ...,
        guest_name=guest_name_to_store,
        guest_email=guest_email_to_store,
        primary_guest_name=primary_guest_name or guest_name,
        primary_guest_email=primary_guest_email or guest_email,
        ...
    )
```

**Agent actions:**
1. Verify the exact current parameter order and every call site (`routes.py`, `events/routes/assignment.py`, any test file) before changing the signature — a positional-argument change can silently break callers that don't use keyword arguments.
2. Implement, preferring keyword-only arguments (`*,`) for everything after `check_out` if not already so, to prevent future silent positional mismatches like the one found in Task 3.
3. Run/update `test_accommodation_booking.py` for both the self and third-party paths with `guest_name=None`.

---

## Task 12 — Verify `/r/<token>` public registration routes exist

**Problem, where found:** `registration_link.html` template is real and looks correct; the Flask route(s) behind it (`GET /r/<token>`, `POST /r/<token>/register`) were designed in Addendum 1 §5.3 but never shown or confirmed to exist.

**Agent actions:**
1. Verify — `grep -rn "def.*registration_link\|'/r/<" app/accommodation/routes.py` (or wherever routes live).
2. If missing, implement per Addendum 1 §5.3 — public, no `@login_required`, rate-limited via the existing `AbusePreventionService` (do not build new rate-limiting).
3. If present, just confirm it uses `RegistrationService.create(..., source='self')` and enforces the `BookingRegistrationLink.is_full` check before rendering the form.

---

## Task 13 — `PropertyBookingPolicy.available_request_options`

**Problem, where found:** Designed in Addendum 1 §3.1 to scope special requests to what a host actually declared they can accommodate. Never confirmed as added to the model.

**Agent actions:**
1. Verify — check `app/accommodation/models/booking_policy.py` for this column.
2. If missing: `available_request_options = Column(JSON, default=list)`, additive migration, safe.
3. Wire into wherever special-request UI chips are rendered (checkout Step 3, confirmation card, dashboard, `registration_link.html`) — all four should read from the same property-level list.

---

## Task 14 — `PropertyPaymentMethod.preferred_currency`

**Problem, where found:** Migration C from the base spec — never directly verified since `property_payment_method.py` itself was never inspected, only referenced indirectly through `payment_policy_service.py`'s queries.

**Agent actions:**
1. Verify — view `app/accommodation/models/property_payment_method.py` directly for the first time in this workstream.
2. If `preferred_currency` is absent: add it (`String(3), nullable=True`, falls back to `Property.currency` when null), additive migration.
3. Update `payment_policy_service.py`'s `get_allowed_options()` to read it into each method's `currency` key (this closes the loop Task 2 depends on).

---

## Task 15 — `checkout.css` class verification

**Problem, where found:** `checkout.html` depends on `.hidden-section`, `.timing-card`, `.badge-timing`, `.payment-method-wrapper`, `.booking-type-card`, `.step-indicator` and others. Never confirmed these exist in the real stylesheet.

**Agent actions:**
1. Verify — `grep` each class name against `static/css/modules/accommodation/checkout.css`.
2. Add any missing class with minimal styling (functional, not necessarily final visual design) so the page isn't unstyled/broken.
3. Do not redesign existing working styles while doing this — additive only.

---

## Task 16 — Apply the `auth_delegations` migration

**Problem, where found:** Migration `4786109b9f92_add_auth_delegations_table.py` reviewed and correct (pending the `requires_approval` server_default fix from the separate small prompt already issued). Never actually run against the database.

**Agent actions:**
1. Verify `alembic heads` returns exactly one head matching `c0758a81e4b0` before upgrading.
2. Apply the `requires_approval` server_default fix first (separate prompt already given) if not yet done.
3. Run `alembic upgrade head` in a non-production environment first; confirm the table exists with `\d auth_delegations` in psql.
4. Only then apply to production.

---

## Task 17 — Load-test the `registration_service.py` row-lock fix

**Problem, where found:** `with_for_update()` added to close the TOCTOU capacity race; never executed under real concurrent load.

**Agent actions:**
1. Verify — write a test that fires N concurrent `RegistrationService.create()` calls at a booking with `num_guests = N-1` (one more request than slots).
2. Confirm exactly `N-1` succeed and 1 raises `ValueError`, never `N` succeeding (over-capacity) and never a deadlock.
3. Confirm the lock doesn't measurably slow down normal (non-concurrent) registration — a lock held too long is its own problem.

---

## Task 18 — Confirm Addendum migrations are applied, not just written

**Problem, where found:** `BookingSpecialRequest`, `BookingRegistrationLink`, and the `GuestRegistration` slot-lifecycle fields (`is_active`, `is_placeholder`, `replaces_registration_id`, etc.) all exist as model code, confirmed in earlier rounds. Migration application state was never confirmed.

**Agent actions:**
1. Verify against the live database schema (`\d accommodation_booking_special_requests`, `\d accommodation_booking_registration_links`, `\d accommodation_guest_registrations` in psql) whether these columns/tables actually exist yet.
2. If not applied, generate the migration(s) via `alembic revision --autogenerate` and review the diff carefully before running — do not blindly trust autogenerate given this codebase's history of drift between model state and migration state.
3. Apply in a non-production environment first.

---

## Completion protocol

After each task: state clearly what was verified, what was changed, and what (if anything) is still unconfirmed or deferred to a later task. Do not mark a task complete if its "Verify" step surfaced a different reality than described here — report the discrepancy instead of forcing the written solution to fit.
