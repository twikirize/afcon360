# KYC Upgrade — Hide Transaction Limits Contract

## Node ID
`KYC-UPGRADE-HIDE-LIMITS`

## Objective
Do not display daily transaction limit amounts on the user-facing KYC upgrade page at `/kyc/upgrade`.

## Scope
- Remove the daily-limit amount card from `templates/kyc/upgrade.html`.
- Remove CSS used only by that amount card.
- Keep tier names, descriptions, document requirements, eligibility state and upgrade actions.
- Do not change tier configuration, server-side transaction-limit enforcement, KYC requirements, or limit APIs.

## User-facing behavior
Each available upgrade card continues to show:
- Tier name and tier number
- Tier description
- Required documents
- Upgrade action when eligible, or the missing requirements/actions when not eligible

Daily transaction-limit amounts and UGX values are not rendered on this page.

## Verification-flow boundary
Verification-code flows remain separate from documentary KYC uploads:
- Email verification uses a six-digit code on the email-verification route.
- Phone verification uses a six-digit OTP delivered through the configured transport (SMS or the account email fallback).
- Documentary requirements for higher KYC tiers continue to use the existing document-upload flow.

The phone-verification template and route are the source of truth for the configured OTP transport. Email and phone verification do not require users to upload identity documents as part of entering the verification code.

## Acceptance criteria
- [ ] `/kyc/upgrade` does not render `upgrade.limits`, the daily-limit card, or UGX limit amounts.
- [ ] Tier names, descriptions, required-document lists and upgrade actions remain present.
- [ ] Server-side limits and enforcement are unchanged by this presentation-only change.
- [ ] Email and phone verification continue to use their existing code-entry flows.
- [ ] Existing document-upload requirements remain available for documentary KYC.

## Regression coverage
`tests/test_kyc_upgrade_display_contract.py` checks that the upgrade template does not reintroduce the daily-limit display and that the core upgrade-card content remains present.
