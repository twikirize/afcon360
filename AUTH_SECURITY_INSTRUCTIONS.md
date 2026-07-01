# AUTH SECURITY AUDIT — INSTRUCTIONS FOR IMPLEMENTING AGENT

## Your Mission
Audit and fix security vulnerabilities in user registration, login, and session handling.
Read these instructions fully before touching any code.

## Files to Audit (in order)
1. `app/auth/routes.py` — registration, login, logout routes
2. `app/auth/services.py` — authenticate_user, register_user
3. `app/auth/session_management.py` — SessionManager class
4. `app/auth/password_policy.py` — PasswordPolicy class
5. `app/auth/otp_service.py` — OTPService class
6. `app/auth/tokens.py` — token generation/verification

---

## Known Vulnerabilities to Find and Fix

### 1. Rate Limiting — LOGIN (CRITICAL)
**File:** `app/auth/routes.py`, login route
**Problem:** `@limiter.limit("100 per minute")` is dangerously high — allows 100 brute-force
attempts per minute per IP.
**Fix:** Change to `"5 per minute"` for POST. Use `"30 per minute"` for GET.
**Pattern to use:**
```python
@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
@limiter.limit("30 per minute", methods=["GET"])
```

### 2. Username Enumeration (HIGH)
**File:** `app/auth/routes.py`, login route + `app/auth/services.py`
**Problem:** Different error messages or timing for "user not found" vs "wrong password"
lets attackers enumerate valid usernames.
**Fix:** Always return the same generic message: `"Invalid credentials."` for both cases.
The `_ct_delay()` helper already exists — confirm it's called on ALL failure paths in
`authenticate_user()`. If not, add it.

### 3. Session Fixation (HIGH)
**File:** `app/auth/session_management.py`, `create_secure_session()`
**Problem:** `session.clear()` then repopulating is good, but Flask-Login's `login_user()`
must be called BEFORE writing to session so Flask regenerates the session ID.
**Fix:** Ensure `login_user(user)` is called before `session.update(...)` in every login
branch inside `app/auth/routes.py`.

### 4. Open Redirect (HIGH)
**File:** `app/auth/routes.py`, login route — `next` parameter handling
**Problem:** The `is_safe_url()` helper exists but verify it is actually called before
every redirect that uses `request.args.get('next')`.
**Fix:** Wrap every `next`-based redirect:
```python
next_url = request.args.get('next')
if next_url and is_safe_url(next_url):
    return redirect(next_url)
return redirect(_dashboard_for_user(user))
```
Never do `redirect(request.args.get('next'))` without validation.

### 5. OTP Hardcoded Pepper (MEDIUM)
**File:** `app/auth/otp_service.py`, `_hash_otp()`
**Problem:** `pepper = "otp_service_pepper"` is hardcoded — if source code leaks,
OTPs can be pre-computed.
**Fix:** Read from config:
```python
pepper = current_app.config.get('OTP_PEPPER', 'otp_service_pepper')
```
Add `OTP_PEPPER` to `.env.example` with a note to set a strong random value in production.

### 6. MFA Bypass on Owner Login (HIGH)
**File:** `app/auth/routes.py`, owner login block
**Problem:** When `REQUIRE_OWNER_MFA=False` and user HAS MFA enabled, if no `mfa_code`
is provided, login still succeeds with a comment about "backward compatibility".
This is a security regression — if a user enrolled MFA, it should always be enforced.
**Fix:** If `user.mfa_enabled`, always require and verify `mfa_code` regardless of
`REQUIRE_OWNER_MFA` config. Config should only control whether MFA *enrollment* is
mandatory, not whether an already-enrolled MFA can be skipped.

### 7. Password Policy Not Enforced at Registration (MEDIUM)
**File:** `app/auth/routes.py`, register route + `app/auth/services.py`
**Problem:** Check whether `PasswordPolicy.validate_password()` is actually called
during `register_user()`. If not, the policy class exists but is never enforced.
**Fix:** In `register_user()` or the register route, call:
```python
from app.auth.password_policy import PasswordPolicy
policy = PasswordPolicy()
is_valid, errors = policy.validate_password(password, {'username': username, 'email': email})
if not is_valid:
    # return errors to user
```

### 8. Session user_id Stores Integer PK (MEDIUM)
**File:** `app/auth/session_management.py`, `create_secure_session()`
**Problem:** `session['user_id'] = user.id` stores the internal BigInt PK in the session
cookie, which violates the identity policy (internal IDs must never be exposed externally).
The login route also does `session["user_id"] = user.public_id` which is correct —
these are inconsistent.
**Fix:** In `create_secure_session()`, change to:
```python
session['user_id'] = str(user.public_id)   # UUID only
# remove: session['user_id'] = user.id
```
Audit all `session.get('user_id')` reads to ensure they handle UUID string, not int.

### 9. Missing CSRF on Login Form (MEDIUM)
**File:** `templates/login.html`
**Check:** Confirm the login form includes `{{ csrf_token() }}` or `{{ form.hidden_tag() }}`.
If missing, add it. CSRF on login prevents login CSRF attacks.

### 10. Security Question Answer Stored Plaintext (MEDIUM)
**File:** `app/auth/services.py` or wherever `security_answer` is saved
**Check:** If `security_answer` is stored in the database, confirm it is hashed
(bcrypt/argon2), not stored as plaintext. If stored plaintext, hash it using
`werkzeug.security.generate_password_hash()` before saving.

---

## What NOT to Do
- Do NOT run `flask db migrate` — ask the user first if a migration is needed
- Do NOT modify `app/wallet/models/`
- Do NOT change `BaseModel`
- Do NOT change the rate limit on `/register` (already at `10 per minute` which is acceptable)
- Do NOT refactor code beyond the specific fixes above

## Project Rules Reminder
- Models inherit from `BaseModel`, FKs use `BigInteger` → `user.id`
- `user.public_id` (UUID) for all external/session/API exposure
- Absolute imports only
- PowerShell: use `;` not `&&` for command chaining
- After changes: report in `AUTH_SECURITY_REPORT.md`

---

## After Implementation
Write your findings and all changes made into:
**`AUTH_SECURITY_REPORT.md`** (in the project root)

Use the report template defined in that file.
