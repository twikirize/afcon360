# DRIVER-ONBOARDING-SINGLE-ENTRY — Contract

**Node:** DRIVER-ONBOARDING-SINGLE-ENTRY  
**Owning domain:** Transport  
**Dependencies:** Authentication, Identity/Profile, KYC, shared cache utility  
**Status:** OWNER-AUTHORIZED — implementation in progress  
**Base:** `main` at `a1bc6e08cd16199bb13124e16984bb71a0130505`  
**Implementation branch:** `fix/driver-onboarding-single-entry-20261115`

> **Owner authorization and governance exception:** The repository's default rule reserves contract authorship to the human owner. The owner has explicitly directed the agent to create this contract and implement it, and expressly waived that authorship restriction for this node. This exception is limited to this node; it does not amend `AGENTS.md`, the shared Operating System, or the rules for future nodes. The owner has authorized backend implementation in this node. No native-app branch or production environment is authorized.

---

## 1. Guarantee

A person who creates an account and proceeds into Driver onboarding will not be asked to re-enter contact or personal identity facts already held by the canonical account/profile records.

The signup phone number is retained as an **unverified contact value**, reused by phone verification, and is never silently marked verified. Email verification and phone verification remain distinct steps with their own correct code-entry screens.

Driver onboarding creates a DriverProfile and Transport provider intention only. It collects the operating market and driving-licence evidence it actually persists. It does not imply that a vehicle was registered. A vehicle is registered separately after driver approval; a driver-owned vehicle registered through that flow is linked to the driver through the canonical active DriverVehicleHistory assignment.

KYC consumes a National Identification Number (NIN) from canonical profile data when one already exists. When it does not exist, the KYC page is the single place where it is collected as evidence. Existing KYC/go-live controls remain authoritative and fail closed; no mock identity or mock criminal-record result may grant eligibility.

The driver vehicle-registration path uses the same Tier-2 KYC threshold already defined for Driver Go-Live. Non-driver personal vehicle registration retains its existing Tier-3 threshold. Driver-purpose KYC upgrade guidance shows only the driver-relevant Tier-2 requirements rather than the general Tier 1–5 ladder.

No database schema change or migration is required.

## 2. Current Behavior

Source trace on the base commit established:

- `/register` captures a phone number and includes it in the pending-registration payload, but the email-OTP account-creation path does not copy it to `User.phone` or `UserProfile.phone_number`. The direct registration path does not pass it to `register_user` at all.
- `/verify-phone` reads only `UserProfile.phone_number`, while the canonical identity service resolves the phone from the profile or `User.phone`. This makes a signup phone appear missing. The phone page's code input is rendered only after email verification and a phone value are available. The optional full-name field creates another identity-entry point.
- `/resend-verification` is for account-email verification, but redirects to the referrer. When invoked from `/verify-phone`, the user returns to the phone page instead of the email-code entry page.
- Driver Step 1 asks for name, date of birth, nationality and NIN even though the commit intentionally treats canonical identity as read-only and discards those values.
- Driver Step 2 collects licence class and a document URL, but only licence number and expiry are saved to DriverProfile.
- Driver Step 3 asks for vehicle details and insurance evidence, but the commit intentionally creates no Vehicle. An existing Stage 4B-5 test protects the resource-free onboarding invariant.
- The KYC National ID page always renders an editable NIN input, even when `UserProfile.id_number` already has the value.
- `/transport/register-vehicle` applies Tier 3 to every owner even though Driver Go-Live is explicitly Tier 2. A successful driver vehicle registration creates the Vehicle but does not create the active DriverVehicleHistory row used by `DriverProfile.current_vehicle`.
- Transport's identity adapter imports a non-existent IdentityService and falls back to fabricated all-green identity data. The criminal-record field is also defaulted to false without an authoritative screening source.
- `SettingsService.is_feature_enabled` calls `set_cached(..., timeout=...)`, but the shared helper's parameter is `ttl`; this causes the feature checks seen in onboarding logs to fall back to their defaults.

## 3. Scope-In

1. Retain signup phone values on both account-creation paths:
   - pending email-OTP registration;
   - direct registration when email verification is not required.
   Store the number in the User and UserProfile contact fields where available. Do not set phone verification flags or timestamps merely because a number was supplied at signup.
2. Make phone verification resolve the already-saved canonical number, accept a number only when none exists, render the existing six-digit code entry after email verification, and return email-resend users to the email verification code page. Remove phone-page collection or mutation of the user's full name.
3. Make Driver Step 1 a read-only canonical identity summary. Driver onboarding must not write identity fields or collect a second copy. If a canonical value is absent, guide the user to the appropriate account/KYC flow rather than saving wizard-local identity.
4. Keep Driver Step 2 licence number, expiry, class and uploaded-document reference in the DriverProfile's existing metadata/fields without a migration.
5. Change Driver Step 3 to collect only the operating country/market. Keep driver onboarding resource-free: no Vehicle, booking, wallet or passenger resource is created there.
6. Make NIN collection single-entry:
   - if canonical `UserProfile.id_number` exists with `id_type == national_id`, show a masked read-only value and use that server-side for NIRA submission;
   - otherwise, allow NIN entry on the KYC page only;
   - do not copy the submitted NIN evidence (`KycRecord.id_number`) back into `UserProfile.id_number`; preserve any existing KYC-first full-name/date-of-birth behavior;
   - preserve the existing pending/verified duplicate-submission guard.
7. Add a driver-purpose KYC-upgrade path that exposes only the Tier-2 requirements needed by Driver Go-Live. Preserve the general KYC upgrade page for other uses.
8. Set the vehicle-registration KYC threshold by owner path: Tier 2 for a user with a DriverProfile; Tier 3 for a non-driver personal vehicle owner. A driver may register only after their DriverProfile is approved, consistent with the existing ProviderService rule.
9. After a driver-owned Vehicle registration succeeds, create its active relationship through `assign_driver_to_vehicle`. Do not write DriverVehicleHistory directly or change the canonical assignment service.
10. Replace fabricated Transport identity data with a read-only projection from the existing canonical User/UserProfile/KYC authorities. Driver-profile participation must not be mislabeled as KYC approval: actual KYC remains enforced by the existing Tier-2 Go-Live check. Continue to enforce active account, verified email, conditional phone verification, a known date of birth and minimum driver age, and fail closed when criminal screening is enabled but no authoritative screening result exists.
11. Correct the `set_cached` argument from `timeout` to `ttl` in Transport SettingsService.
12. Add focused regression tests in node-owned test files. Update only local test helpers if the stricter real account-state contract requires them; do not change shared fixtures.

## 4. Scope-Out

- No change to native User APK, native Driver APK, their branches, mobile build workflows, OTA/Firebase configuration, or React Native code.
- No change to wallet, ledger, payment, booking, ride lifecycle, matching, dispatch, pricing or unrelated provider capabilities.
- No new identity/KYC tables, columns, enums, indexes or other schema changes.
- No generated or manual database migration; no `flask db migrate`, `flask db upgrade`, seed, or production database action.
- No change to the global KYC Tier definitions or the existing Driver Go-Live Tier-2 decision.
- No weakening of DriverProfile compliance approval, blocked-state, valid-licence, assigned-vehicle or dispatch eligibility checks.
- No automatic vehicle creation at driver onboarding, and no change to the separate Vehicle ownership model.
- No fabricated NIRA, phone, email, identity, age or criminal-screening verification.
- No changes to shared test fixtures `tests/conftest.py` or `tests/setup_owner.py`, `app/models/base.py`, or the register.
- No edits to the draft SUPPLY-ELIGIBILITY node or reopening any closed node.

## 5. Interface Contract

### Account registration and contact verification
- `register_user(..., phone=...)` accepts an optional phone value without breaking existing callers.
- Pending registration payload's phone survives email OTP verification.
- `User.phone` and `UserProfile.phone_number` represent the saved contact value; phone verification flags remain false until the phone-verification OTP succeeds.
- `GET /verify-phone` resolves phone from canonical profile/user sources.
- `GET /resend-verification` for an unverified email redirects to `/verify-email`, where the account-email code is entered.
- Phone verification remains a separate six-digit OTP purpose and does not update full_name.

### Driver onboarding
- Step 1 is a read-only identity summary from UserProfile.
- Step 2 submits licence number, expiry, class and optional evidence URL. The number/expiry remain in DriverProfile's existing canonical licence fields; class/evidence reference are persisted to existing `driver_metadata`.
- Step 3 submits only `operating_country_code` (currently UG, KE or TZ).
- Commit creates DriverProfile and Transport provider intention only.

### KYC and vehicle registration
- KYC National ID POST uses canonical `id_number` only when canonical `id_type` is `national_id`; otherwise it requires the submitted NIN.
- Driver-purpose upgrade is selected by `purpose=driver` and ends at Tier 2; general upgrades remain unchanged.
- Driver-owned vehicle registration requires Tier 2 and approved DriverProfile; non-driver personal registration requires Tier 3.
- Driver-owned vehicle registration creates exactly one active assignment through `assign_driver_to_vehicle(driver, vehicle, reason, authorized_by, notes)`.

### Identity and settings
- Transport identity is derived from real account/profile/KYC records. Missing IdentityService must not produce synthetic verified facts.
- If criminal-record screening is enabled but no authoritative result is available, driver registration fails closed with a service-unavailable error.
- Settings caching calls `set_cached(key, value, ttl=...)`.

## 6. Proof of Done

Run from a clean backend checkout with the project's configured environment and **only** the isolated `afcon360_test` database:

1. `pytest tests/test_phone_verification.py -q`
2. `pytest tests/test_stage4b5_transport.py -q`
3. The new node-owned driver-onboarding/KYC/identity regression tests, individually and together.
4. Relevant existing transport and KYC route tests identified by search.
5. `python -m compileall app/auth app/transport app/kyc`
6. Confirm by source/test assertions that Driver onboarding creates no Vehicle and no wallet/booking/passenger resource; separate driver vehicle registration does create one active history assignment.
7. Confirm by tests that signup phone remains unverified until phone OTP success; email resend leads to the email code form; phone OTP is distinct; NIN is not re-entered when canonical; missing canonical NIN is collected once; the driver upgrade screen contains no Tier 3–5 offers; and non-driver vehicle registration still has Tier-3 enforcement.
8. Confirm the mock identity branch is absent and a missing criminal-screening authority fails closed when the feature is enabled.
9. Confirm no migration, schema, wallet, mobile or shared-fixture diff exists.

Passing the automated commands is necessary but not sufficient. The owner must verify the final branch on a clean local checkout against the isolated test database and confirm PASS before evidence/record creation or register updates.

## 7. Rollback

- Revert the node commit(s) on `fix/driver-onboarding-single-entry-20261115`; do not revert or amend `main`.
- If an unexpected route or onboarding regression appears, revert this node's backend changes as one unit and restore the previous branch head.
- There is no schema change, so rollback requires no database downgrade or data restoration.
- Do not merge the branch until the proof commands pass and the owner has reviewed the diff.

## 8. Constraints

- This is a backend-only node. The User APK and Driver APK branches are not to be checked out, changed, merged, rebuilt or republished.
- Work stays on `fix/driver-onboarding-single-entry-20261115`, based on the recorded main SHA.
- No secrets, OTP values, personal NINs or user-specific contact values may be copied into tests, contract, evidence or logs.
- Existing domain services are authoritative. Use `get_canonical_identity`, `calculate_kyc_tier`, `assign_driver_to_vehicle`, and the existing phone verification service; do not create parallel authorities.
- Keep driver workspace participation distinct from Go-Live. KYC Tier 2 and compliance approval remain required to go live; vehicle assignment is required for on-demand service.
- No database writes or migrations are performed by the agent. Tests must use `afcon360_test` only.
- The owner expressly authorizes the KYC route/template edits described in Scope-In, notwithstanding the normal KYC-code red line. No other KYC behavior is authorized.
- The owner expressly authorizes the agent to author this contract as a one-node exception to the human-authored-contract rule. This is not a standing governance amendment.

## 9. Acceptance Criteria

- [ ] Signup phone is saved on pending and direct registration paths as unverified contact data.
- [ ] Phone verification pre-fills the existing number, provides a visible six-digit code input after account email verification, and does not ask for or change full name.
- [ ] Resending account-email verification from phone onboarding opens the email-code entry flow, not the phone page.
- [ ] Driver Step 1 contains no editable duplicate identity/NIN inputs and reflects canonical profile data read-only.
- [ ] Driver Step 2 persists licence number, expiry, class and optional document reference.
- [ ] Driver Step 3 asks only for operating market; the initial commit remains resource-free.
- [ ] KYC NIN is read-only/masked when canonical `id_type` is `national_id`; passport/driver-licence numbers are never mistaken for NIN; POST cannot override a canonical NIN.
- [ ] Driver-purpose KYC upgrade shows only Tier-2 driver requirements and a clear completed state once Tier 2 is met.
- [ ] Driver vehicle registration enforces Tier 2 plus approved DriverProfile; non-driver personal vehicle registration continues to enforce Tier 3.
- [ ] A registered driver-owned vehicle is assigned by the canonical history service and becomes DriverProfile.current_vehicle.
- [ ] Transport no longer invents all-green identity data. Account/email/conditional-phone/age rules use real records, and enabled-but-unavailable criminal screening fails closed.
- [ ] The settings feature-flag cache no longer raises an unexpected `timeout` argument error.
- [ ] Focused regression tests and compile checks pass; no schema/migration, wallet, mobile, shared-fixture or out-of-scope diff exists.
