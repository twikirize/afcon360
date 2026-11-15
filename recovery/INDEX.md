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
| Recovery index | `audit/recovery-review-20261116` | Review ledger and constraints |

The latest versions of the currency service files and heatmap JS/CSS/template/routes were checked for common high-confidence token/private-key signatures; none were found in those current file contents. This is not a full historical secret scan.

## Local material still to transfer from Windows

| Source | Current finding | Action |
|---|---|---|
| Detached User EAS commit `f0db1e3b` | 0 commits ahead / 125 behind `feat/native-user-app-integration-20261108`; its app-level User and Driver EAS configs already exist on the remote branch | Do not upload this stale commit as another branch |
| Detached EAS worktree's `mobile/pnpm-lock.yaml` | Untracked locally; not present on the remote User integration branch | Compare with workspace manifests, then snapshot to this recovery workspace |
| Root `eas.json` | Untracked locally | Inspect contents and confirm placement; snapshot only after checking it contains no credentials |
| `integration/backend-main-consolidation-20261112` | Local tip `f095be91` is not currently available through GitHub API; branch is locally ahead by one and behind by six | Push to a separate audit ref after local secret screening |
| Other dangling commits | Several WIP, Celery, notifications, native events and infrastructure commits identified | Preserve useful commits with audit refs/tags after content and secret screening |

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
