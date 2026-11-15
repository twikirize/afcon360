# AFCON360 recovery review — 2026-11-16

This branch is an isolated review workspace. It is not a deployment branch and must not be merged into `main` wholesale.

## Already preserved on GitHub

| Source | Remote reference | Review note |
|---|---|---|
| Local main at `b0a345e6` | `audit/local-snapshot-20261115-224848` | Preserves local-only commits; older KYC/account-closure implementations are superseded and must not be promoted blindly |
| Stash 0 | `audit/stash-0-20261115` | KYC, transport and test snapshots; older KYC backfill needs transaction-safety review |
| Stash 1 | `audit/stash-1-20261115` | KYC/profile snapshots; older profile/account-closure flows are not presumed safe |
| Stash 2 | `audit/stash-2-20261115` | Provider-service snapshot; stale identity fallback and age-check weaknesses identified |
| Old base template | `audit/old-base-template-20261116` | Preserved for later comparison; do not replace current `templates/base.html` |

## Local-only work to transfer and inspect

| Local reference or file | Known value | Required action |
|---|---|---|
| Currency/home-currency work | `ef89674e` on `feat/usd-pricing-home-currency-20261104` | Compare with current main; scan changed files before publishing |
| Driver heatmap work | `9ec1b6c8` on two local branch aliases | Publish one canonical audit ref after reviewing diff |
| User EAS setup | `f0db1e3b`, detached worktree | Inspect commit and untracked lockfile; keep separate from backend main |
| Root EAS config | untracked `eas.json` | Inspect content and secret risk; do not assume it belongs at repository root |
| User pnpm lockfile | untracked `mobile/pnpm-lock.yaml` in EAS worktree | Compare against app workspace lockfile before publishing |
| Other local branch / dangling commits | See local audit inventory | Publish only after file-level review and secret screening |

## Constraints

- Never merge this branch wholesale into `main`.
- No force pushes, hard resets, stash drops, pruning, or deletion during recovery.
- Do not publish credentials, signing keys, private certificates, tokens, environment files, or other secrets.
- Keep User/Driver native-app integration work separate from backend main.
- Preserve original commit history where practical; use review branches rather than flattening unrelated histories.
- Promote only reviewed, relevant changes through focused pull requests.

## Review outcomes

Each candidate will be marked as one of:
1. Already incorporated in current main.
2. Preserve for later development.
3. Recover through a focused change / pull request.
4. Superseded or safe to retire after confirmation.
