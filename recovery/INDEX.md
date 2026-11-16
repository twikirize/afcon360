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


## Local dangling-commit inventory — 2026-11-16

A read-only PowerShell audit on the Windows checkout inspected 27 candidate commit objects against the then-fetched `origin/main` commit `2f6f05d6e5c80c7a172ec90232bdc120b97fca11`.

- All 27 object IDs resolved locally.
- None was an ancestor of that `origin/main` snapshot.
- The script's reference check covered `refs/heads`, `refs/remotes`, and `refs/tags` only. It did **not** inspect `refs/stash`, other refs, or reflogs. Therefore do not conclude that every object is wholly unreferenced until a broader reference/reflog audit is run.
- No repository files, branches, tags, stashes, or remote refs were changed by the audit script.

### Initial disposition based on changed paths and a read-only inspection of current main at the audited SHA

| Candidate | Finding | Disposition |
|---|---|---|
| `0302f9ef`, `d8dd6eb8` | Both are WIP-style commits with the same six KYC/profile paths and identical reported change counts (299 insertions / 44 deletions), but they have different second parents. Patch identity has not yet been proved. | Keep both objects until exact patch comparison and `refs/stash` / reflog inventory. Inspect the KYC/profile changes only under an explicit contract; current AGENTS.md prohibits KYC edits without one. |
| `1047eb74` | Production console streaming and DB/Socket.IO contract tests. Current main has `app/production_console/streaming.py`, `tests/test_db_credential_contract.py`, and `tests/test_socketio_queue_contract.py`. The current implementation uses realtime readiness guards and log redaction. | Appears represented/evolved in current main. No wholesale port; retain object until direct patch comparison. |
| `5c8e5462`, `9ea6366f` | Twilio SMS/WhatsApp / OTP drafts. Current main has Twilio SMS handler, owner Twilio routes, and the SMS/WhatsApp owner section. | The current feature is present in evolved form. Do not restore the older drafts. Never port the two migration files from `5c8e5462`; migration governance remains unchanged. |
| `a6a18efd` | Driver dashboard / MapLibre work and dashboard previews. Current main has the driver map, dashboard comparison, and dashboard-version paths. | Feature paths are represented in current main. Do not restore preview files or the entire old snapshot; only review any demonstrably missing functional fix. |
| `0abb8d0f` | Model-bootstrap/favicon work. Current main has favicon assets and the model-bootstrap contract test. | Appears represented/evolved; no duplicate port without a specific missing behavior. |
| `9b6e7b3f` | DriverProfile FK contract. Current main's model uses a table-level `ForeignKeyConstraint`, and the contract test exists. | Appears represented/evolved; no duplicate port. |
| `1efeaad0` | Agent-onboarding server defaults and test. Current main has server defaults on the relevant status/deletion columns and the dedicated test. | Appears represented/evolved; no duplicate port. |
| `b23b86fb` | Observability/CAS/notification ETag change. Current main's notifications unread-count route has an ETag and private cache-control response. | ETag portion is represented. CAS / app-initialization changes still require direct patch comparison before disposition. |
| `efda0af6` | Offsite backup test (155 lines in candidate). Current main has a larger `tests/test_backup_offsite.py` with upload/download checksum verification and configuration checks. | Test coverage is present in an evolved form; no duplicate port. |
| `62b9275f`, `c05fd34a` | Large H3 / production-console WIP snapshots; `62b9275f` touches 31 paths and contains candidate migration tooling, while `c05fd34a` includes a misplaced nested candidate migration path. | Preserve for later source inspection only. Do not merge either snapshot wholesale, do not modify root migration history, and do not transplant handwritten migration files. |
| `89f2a526` | Adds `app/events/routes/assignment.py` (441 lines); that path is absent from current main at the audited SHA. | Preserve as an unintegrated feature candidate. Review authorization, service boundaries, idempotency, booking lifecycle, and tests before deciding whether to recover. |
| `45f1ad5f` | Two-line Wallet payer identity change. Current main has a substantially developed Wallet marketplace invoice service, but exact behavior equivalence is not yet proved. | Preserve pending exact diff comparison; Wallet changes require an explicit contract. |
| `23dc1b8f` | Adds 73 lines to an owner MFA recovery security test file. The exact old test path was not found on current main. | Preserve and inspect against current MFA recovery tests; do not assume coverage is missing until alternate test paths are checked. |
| `602000bc` | WIP migration-governance guidance change in AGENTS.md. | Keep as historical policy evidence; compare to current AGENTS.md before any documentation port. |
| `e4cf3775`, `333dca34`, `946b2b45`, `be6e7579`, `3c6f39fd`, `e6dcddf4`, `d5e29918`, `d4e91535`, `f6f2155f`, `08f79dda` | Small app-initialization, test, workflow, and documentation amendments. | Retain until the exact current-main diffs are checked; do not promote individually based only on commit titles. |

These are initial content-presence checks, not proof that every old blob is byte-identical to current main. Exact patch comparison and the broader refs/reflog check remain open.
