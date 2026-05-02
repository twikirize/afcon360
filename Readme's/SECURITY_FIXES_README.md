# AFCON360 Security Fixes - Action Plan

> **Status:** CRITICAL - Do not deploy until all CRITICAL issues are resolved  
> **Last Updated:** April 30, 2026  
> **Auditor:** Security Audit (AI Analysis)

---

## Quick Stats

| Severity | Count | Fixed | Remaining |
|----------|-------|-------|-----------|
| CRITICAL | 7 | 0 | 7 |
| HIGH | 11 | 0 | 11 |
| MEDIUM | 8 | 0 | 8 |
| LOW | 4 | 0 | 4 |

**Deployment Readiness:** 3/10  
**Can Deploy Today:** NO

---

## CRITICAL Issues (Fix First)

### C1: Debug Mode Enabled in Production Entry Point
- **File:** `app.py:19`
- **Risk:** Stack traces exposed, Werkzeug console allows code execution
- **Fix:**
  ```python
  # BEFORE:
  if __name__ == "__main__":
      app.run(debug=True, use_reloader=False)
  
  # AFTER:
  import os
  if __name__ == "__main__":
      debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
      app.run(debug=debug_mode, use_reloader=False)
  ```
- **Verification:** Run app, ensure no debugger pin appears in console
- **Time:** 0.5 hours  
- **Status:** [ ] Not Started | [ ] In Progress | [ ] Complete

---

### C2: Wildcard CORS on Financial API
- **File:** `app/wallet/api/wallet_api.py:895-901`
- **Risk:** Any website can make authenticated requests to wallet API
- **Fix:**
  ```python
  @wallet_api_bp.after_request
  def add_cors_headers(response):
      allowed_origins = current_app.config.get('ALLOWED_ORIGINS', '').split(',')
      origin = request.headers.get('Origin')
      if origin in allowed_origins:
          response.headers['Access-Control-Allow-Origin'] = origin
          response.headers['Access-Control-Allow-Credentials'] = 'true'
      response.headers['Access-Control-Allow-Headers'] = 'Authorization, Content-Type, X-Idempotency-Key'
      response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
      return response
  ```
- **Config Update:** Add to `.env`:
  ```
  ALLOWED_ORIGINS=https://app.afcon360.com,https://admin.afcon360.com
  ```
- **Verification:** Test API from unauthorized origin, should be blocked
- **Time:** 1 hour  
- **Status:** [ ] Not Started | [ ] In Progress | [ ] Complete

---

### C3: Pickle Deserialization of Untrusted Data (RCE)
- **File:** `app/wallet/middleware/idempotency.py:67-68, 94-99`
- **Risk:** Remote code execution if Redis is compromised
- **Fix:**
  ```python
  # BEFORE:
  import pickle
  response_data = pickle.loads(cached_response)
  # ...
  self.redis.setex(request.idempotency_cache_key, ttl, pickle.dumps(response_data))
  
  # AFTER:
  import json
  response_data = json.loads(cached_response.decode('utf-8'))
  # ...
  self.redis.setex(
      request.idempotency_cache_key,
      ttl,
      json.dumps(response_data).encode('utf-8')
  )
  ```
- **Verification:** Test idempotency middleware still works, check Redis contains JSON not binary
- **Time:** 1 hour  
- **Status:** [ ] Not Started | [ ] In Progress | [ ] Complete

---

### C4: MD5 Used for Cache Key Generation
- **File:** `app/utils/caching.py:104, 144`
- **Risk:** Collision attacks, cache poisoning
- **Fix:**
  ```python
  # Line 104:
  return f"cache:{hashlib.sha256(key_string.encode()).hexdigest()}"
  
  # Line 144:
  lock_key = f"lock:{func.__name__}:{hashlib.sha256(str(args).encode() + str(kwargs).encode()).hexdigest()}"
  ```
- **Verification:** Search codebase for any remaining MD5 usage
- **Time:** 0.5 hours  
- **Status:** [ ] Not Started | [ ] In Progress | [ ] Complete

---

### C5: Missing Content Security Policy Headers
- **File:** `app/__init__.py` (security headers section)
- **Risk:** XSS attacks possible
- **Fix:** Add to security headers handler:
  ```python
  response.headers['Content-Security-Policy'] = (
      "default-src 'self'; "
      "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
      "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
      "img-src 'self' data: https:; "
      "font-src 'self' https://fonts.gstatic.com; "
      "connect-src 'self'; "
      "frame-ancestors 'none'; "
      "base-uri 'self'; "
      "form-action 'self';"
  )
  ```
- **Verification:** Check response headers in browser dev tools
- **Time:** 1 hour  
- **Status:** [ ] Not Started | [ ] In Progress | [ ] Complete

---

### C6: Missing CSRF Protection on Wallet API
- **File:** `app/wallet/api/wallet_api.py` (POST endpoints)
- **Risk:** CSRF attacks on financial transactions
- **Fix:**
  ```python
  from flask_wtf.csrf import validate_csrf
  
  @wallet_api_bp.route('/transfer', methods=['POST'])
  @login_required
  @require_wallet_enabled
  def transfer():
      # Validate CSRF if using cookie-based auth
      csrf_token = request.headers.get('X-CSRF-Token')
      if not csrf_token:
          return jsonify({"status": "error", "code": "CSRF_TOKEN_REQUIRED"}), 400
      try:
          validate_csrf(csrf_token)
      except Exception:
          return jsonify({"status": "error", "code": "INVALID_CSRF_TOKEN"}), 403
      # ... rest of function
  ```
- **Verification:** API requests without CSRF token should be rejected
- **Time:** 2 hours  
- **Status:** [ ] Not Started | [ ] In Progress | [ ] Complete

---

### C7: Race Condition in Wallet Balance Check
- **File:** `app/wallet/services/wallet_service.py:697-714`
- **Risk:** Overdraft/negative balance possible
- **Fix:**
  ```python
  def _do_transfer():
      # Lock in consistent order FIRST
      if sender.id < receiver.id:
          locked_sender = self.wallet_repo.get_by_user_id(from_user_id, for_update=True)
          locked_receiver = self.wallet_repo.get_by_user_id(to_user_id, for_update=True)
      else:
          locked_receiver = self.wallet_repo.get_by_user_id(to_user_id, for_update=True)
          locked_sender = self.wallet_repo.get_by_user_id(from_user_id, for_update=True)
      
      # Then check balance on locked rows
      sender_version = locked_sender.version
      # ... rest of checks
  ```
- **Verification:** Load test with concurrent transfers between same users
- **Time:** 3 hours  
- **Status:** [ ] Not Started | [ ] In Progress | [ ] Complete

---

## HIGH Priority Issues (Fix After Critical)

### H1: Missing Idempotency Key Validation in Withdraw
- **File:** `app/wallet/services/wallet_service.py:538-632`
- **Status:** [ ] Not Started | [ ] In Progress | [ ] Complete

### H2: Insufficient Webhook Signature Validation
- **File:** `app/wallet/api/webhook_api.py`
- **Status:** [ ] Not Started | [ ] In Progress | [ ] Complete

### H3: Broad Exception Handling Hiding Bugs
- **File:** `app/admin/owner/security_service.py:45-47, 128-129`
- **Status:** [ ] Not Started | [ ] In Progress | [ ] Complete

### H4: No Rate Limiting on Wallet API Endpoints
- **File:** `app/wallet/api/wallet_api.py`
- **Fix:** Add `@limiter.limit("10 per minute")` to all financial endpoints
- **Status:** [ ] Not Started | [ ] In Progress | [ ] Complete

### H5: Debug Code in Production Routes
- **File:** `app/auth/routes.py:471-473`
- **Fix:** Remove or use proper logging
- **Status:** [ ] Not Started | [ ] In Progress | [ ] Complete

### H6: SMS Service Not Imported Before Use
- **File:** `app/auth/routes.py:345-346`
- **Fix:** Add `from app.services.sms_service import SMSService` at module level
- **Status:** [ ] Not Started | [ ] In Progress | [ ] Complete

### H7: Missing Input Validation on Booking Creation
- **File:** `app/transport/services/booking_service.py:63`
- **Status:** [ ] Not Started | [ ] In Progress | [ ] Complete

### H8: Cache Invalidation Race Condition
- **File:** `app/transport/services/booking_service.py:397-403`
- **Status:** [ ] Not Started | [ ] In Progress | [ ] Complete

### H9: Missing Database Transaction Rollback
- **File:** `app/events/services.py:512-515`
- **Status:** [ ] Not Started | [ ] In Progress | [ ] Complete

### H10: Floating Point in Financial Calculations
- **File:** `app/transport/services/booking_service.py:99, 184`
- **Status:** [ ] Not Started | [ ] In Progress | [ ] Complete

### H11: Email Verification Bypass for Owners
- **File:** `app/auth/routes.py:439-468`
- **Fix:** Add MFA requirement for owners
- **Status:** [ ] Not Started | [ ] In Progress | [ ] Complete

---

## Testing Checklist

After fixing each issue, verify:

- [ ] Application starts without errors
- [ ] Related functionality works correctly
- [ ] No new warnings in logs
- [ ] Security headers present (if applicable)
- [ ] Rate limiting active (if applicable)

---

## Pre-Deployment Verification

Before deploying to production, confirm:

- [ ] All CRITICAL issues fixed
- [ ] All HIGH issues fixed OR documented with acceptance
- [ ] `FLASK_DEBUG=False` in production environment
- [ ] `ALLOWED_ORIGINS` configured correctly
- [ ] Redis connection secured
- [ ] Database migrations tested
- [ ] Security headers verified with browser tools
- [ ] Rate limiting tested with load generator

---

## Notes

### Files to Never Commit
- `.env` (contains secrets)
- `flask_session/` folder
- Any files with `_backup` in name to production

### Environment Variables Required
```bash
# Security
SECRET_KEY=<strong-random-key>
ENCRYPTION_KEY=<32-char-key>
FLASK_DEBUG=False

# CORS
ALLOWED_ORIGINS=https://yourdomain.com

# Database
DATABASE_URL=<production-db>

# Redis
REDIS_URL=<production-redis>
```

---

## Progress Log

| Date | Issue | Status | Fixed By | Notes |
|------|-------|--------|----------|-------|
| 2026-04-30 | - | Started | - | Audit complete, fixes ready |
| | | | | |

---

## Questions?

If you're unsure about any fix:
1. Check the original audit report
2. Test in development first
3. Review Flask security best practices
4. Consult OWASP guidelines

---

**Remember:** Never deploy with debug mode enabled or wildcard CORS on financial endpoints.
