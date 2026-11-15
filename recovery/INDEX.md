# AFCON360 recovery review — 2026-11-16

This is an isolated review workspace, not a deployment branch. Do not merge it wholesale into `main`.

## Preserved snapshots already on GitHub

| Source | Remote reference | Review note |
|---|---|---|
| Local main at `b0a345e6` | `audit/local-snapshot-20261115-224848` | Preserves local-only commits; old KYC/account-closure versions are superseded and must not be promoted blindly |
| Stash 0 | `audit/stash-0-20261115` | KYC, transport and test snapshots; old KYC backfill needs transaction-safety review |
| Stash 1 | `audit/stash-1-20261115` | KYC/profile snapshots; old profile/account-closure flows are not presumed safe |
| Stash 2 | `audit/stash-2-20261115` | Provider-service snapshot; stale identity fallback and age-check weaknesses identified |
| Old base template | `audit/old-base-template-20261116` | Preserved for later comparison; do not replace current `templates/base.html` |

## Recovery refs restored on GitHub

| Source | Remote reference | Scope and disposition |
|---|---|---|
| Currency/home-currency work, tip `ef89674e` | `audit/recovery-currency-home-currency-20261116` | 64 commits ahead / 459 behind current main; 24 changed paths. Preserve as a source branch; port only reviewed pieces onto current main |
| Driver heatmap work, tip `9ec1b6c8` | `audit/recovery-driver-heatmap-20261116` | 2 commits ahead / 392 behind current main; 5 changed paths. Preserve as a source branch; review route/API compatibility before porting |
| Local EAS source snapshots | `audit/recovery-local-files-20261116` | Uploaded and verified. Commit `3acec884` adds root EAS JSON, User mobile pnpm lockfile and README; follow-up `5bb5ec8b` only normalizes README text |
| Recovery index | `audit/recovery-review-20261116` | Review ledger and constraints |

The currency service files and heatmap JS/CSS/template/routes were checked for common high-confidence token/private-key signatures; none were found in those current file contents. The two EAS files were checked locally against common credential signatures, and the uploaded files were verified remotely. These checks are not a guarantee that no secret is present in older history.

## EAS and native workspace assessment

- Uploaded `root-eas.json` is a 344-byte source snapshot. It defines `cli.version >= 27.10.0`, with development/preview/production profiles. Keep it as an audit artifact; do not copy it into the backend root or replace the native app configs without confirming the project root used by build commands.
- The existing User and Driver app configs on `feat/native-user-app-integration-20261108` each define app-specific `development`, `preview`, `production`, and `apk-share` profiles. They are the relevant current app-level configuration candidates.
- The uploaded `mobile/pnpm-lock.yaml` is lockfile v9 and contains workspace importers for `apps/user`, `apps/driver`, and packages. The current integration branch contains `mobile/pnpm-workspace.yaml` and app manifests but no root `mobile/pnpm-lock.yaml`; the uploaded lockfile therefore remains a source candidate to validate, not yet the authoritative workspace lock.

## Backend consolidation branch review

The local-only commit `f095be9177f36f2918542a3c1399782bffb079bd` (`Improvement in transport styling for mobile and css`, 2026-11-13) is already incorporated into current `main` through PR #95, merged on 2026-11-13.

Verified:
- PR #95 head was `fix/transport-mobile-css-20261113`; merge commit `50c108466df6a7f0b4eee945bcfbb9e8ad6c114d`.
- The exact blob SHA for `static/css/modules/transport/mobile-booking.css` matches between the local-only commit and current `main`.
- The exact blob SHA for `templates/transport/new_home.html` matches.
- The exact blob SHA for `tests/conftest.py` matches, including the `APP_ENV=testing` assignment.
- Remote audit ref `audit/recovery-backend-integration-20261116` points exactly to commit `f095be9177f36f2918542a3c1399782bffb079bd`.

Disposition: **already incorporated / duplicate snapshot**. Keep the audit ref as evidence during recovery. Do not create another PR or re-merge these files. The local branch may be retired only after the wider local branch/worktree audit is complete and the remote audit ref remains available.

## Local material still to transfer from Windows

| Source | Current finding | Action |
|---|---|---|
| Detached User EAS commit `f0db1e3b` | 0 commits ahead / 125 behind `feat/native-user-app-integration-20261108`; the User server-settings change is already behind current User integration work | Do not upload this stale commit as another branch |
| `integration/backend-main-consolidation-20261112` | Local tip `f095be91` is not currently available through GitHub API; branch is locally ahead by one and behind by six | Inspect the one local-only commit's changed paths and scan before pushing to a dedicated audit ref |
| Other dangling commits | WIP, Celery, notifications, native events and infrastructure commits identified | Preserve useful commits with audit refs/tags after content and secret screening |

## Additional dangling-commit review

These commit objects are addressable in the GitHub repository. Their direct changes have been compared with current `main`; do not create broad branches from their old ancestry without reviewing all included commits.

| Commit | Direct change | Current-main finding | Disposition |
|---|---|---|---|
| `9c11c3ef` | Adds bounded Celery task modules and delivery tests to the focused transport CI workflow | Current workflow already lists the corresponding task modules and Celery/notification tests, with a broader focused test target set | Direct patch is superseded; retain the commit for ancestry review because the compared history contains 31 non-main commits |
| `a522f3c4` | Defers OCI Email credential resolution until configured delivery, with a regression test | Current OCI handler has a stronger authenticated OCI metadata validation path; the same deferral test remains, with additional fallback coverage | Superseded/evolved; do not transplant the older handler |
| `c020b6cf` | Adds bearer-native event API tests and a service change | All seven original test cases remain in current main, with an additional paid-ticket guard test; service logic has evolved its remaining-seat handling | Already represented/evolved; no duplicate port |
| `209c680e` | Adds PostgreSQL-version handling for H3-A baseline and regression tests | `tests/test_h3_baseline_pg_version_compat.py` has an identical blob in current main; H3-A is recorded as the active root migration path | Preserve migration history; do not create a second baseline or hand-edit migration files |
| `1e8a8f7f` | Adds `tests/test_backup_offsite.py` to focused CI targets | Current workflow already includes the offsite backup test in its focused targets and syntax checks | Already incorporated; no cherry-pick |
| `17830c35` | Separates Flask and Celery configuration namespaces | Current `app/celery_app.py` retains explicit `broker_url` / `result_backend` configuration and adds later constrained-worker/context handling | Superseded by current implementation; don't restore old file |
| `317ab78c` | Loads `AuthConfiguration` before staging Twilio/OTP settings | Current owner routes already load the configuration before `SystemConfig.set(..., commit=False)` operations | Already incorporated; no cherry-pick |
| `73dc3a48` | Removes the standalone workspace switcher and improves account dropdown context roles | Current base template uses the newer account-dropdown context component and role reset flow | Superseded by current navigation implementation; old template remains separately preserved |

Some of these commit SHAs have long ancestry outside current main (e.g. 31, 250 and 33 commits in the relevant comparisons). Their direct one-file patches being superseded does **not** mean every ancestor commit is obsolete. Keep the local dangling objects and inspect their commit trees before any branch retirement.

## Constraints

- Never merge this branch or a recovery source branch wholesale into `main`.
- No force pushes, hard resets, stash drops, pruning, or deletion during recovery.
- Do not publish credentials, signing keys, private certificates, tokens, environment files, or other secrets.
- Keep User/Driver native-app work separate from backend main.
- Preserve original commit history where practical.
- Promote only reviewed, relevant changes through focused pull requests.

## Review outcomes

Each candidate will be classified as:
1. Already incorporated in current main.
2. Preserve for later development.
3. Recover through a focused change / pull request.
4. Superseded or safe to retire after confirmation.
