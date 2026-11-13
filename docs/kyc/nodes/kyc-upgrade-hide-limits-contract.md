# KYC Upgrade - Hide Limits Contract

## Node ID
KYC-UPGRADE-HIDE-LIMITS

## Objective
Hide daily transaction limits (money amounts) from the user-facing KYC upgrade page at `/kyc/upgrade`. Phone/email verification should not ask for document uploads.

## Scope
- Modify `templates/kyc/upgrade.html` to remove daily limit display
- Verify phone/email verification flows already use OTP (no document uploads)

## Changes Made

### Template Changes (`templates/kyc/upgrade.html`)
1. Removed `.upgrade-card__limits` div showing "Daily limit UGX {amount}"
2. Removed associated CSS styles for `.upgrade-card__limits` and `.limit-row`
3. Upgrade cards now show only:
   - Tier name and description
   - Required documents list
   - Upgrade button (if eligible) or missing requirements with action links

### Verification Flows (Already Correct)
- `phone_verified` → `auth.verify_phone` (OTP via email/SMS)
- `full_name` → `auth.verify_phone` (collected during phone verification)
- Document requirements → appropriate upload pages

## Acceptance Criteria
- [x] Users at `/kyc/upgrade` see no UGX amounts or daily limits
- [x] Phone verification uses OTP code entry (no document upload)
- [x] Email verification uses OTP code entry (no document upload)
- [x] Application starts successfully (DB_VERIFY_OK)

## Evidence
- Template modified: removed limits display section
- Application startup verified: DB_VERIFY_OK
- Phone verification template (`templates/auth/verify_phone.html`) confirms OTP-only flow