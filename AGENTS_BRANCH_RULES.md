# AFCON360 React Native User App — Branch Constitution for Agents

**Effective:** 2026-11-23  
**Authority:** This document governs all agent work in the User app repository.  
**Repository:** `C:\Users\OBED\Desktop\afcon360-user-dev` (only)

---

## 1. Branch Structure — Immutable

| Role | Branch | Purpose |
|------|--------|---------|
| **Protected Baseline** | `feat/native-user-app-integration-20261108` | Stable integration destination. **Never commit directly.** All changes enter via PR. |
| **Retained Working Branch** | `reconcile/user-local-files-20261121` | Cumulative development branch. **All active work happens here.** |
| **Consolidation Route** | PR #128 | Open PR: `reconcile/user-local-files-20261121` → `feat/native-user-app-integration-20261108`. Must pass all required checks before merge. |

**No other branches** are authorized for User app development. Do not create, push, or merge to any other branch.

---

## 2. Why This Structure Exists

| Problem | Solution |
|---------|----------|
| Multiple competing branches (`feat/native-mobile-apps-20261104`, `feat/native-user-app-integration-20261108`, `feat/user-offline-first-foundation-20261117`, etc.) caused confusion about which was "main" | Single protected baseline (`feat/native-user-app-integration-20261108`) is the **only** integration target |
| Work was fragmented across branches, hard to track | Single working branch (`reconcile/user-local-files-20261121`) accumulates **all** cumulative changes |
| No clear merge gate | PR #128 with **required CI checks** is the only path to baseline |
| Agents worked in wrong repo (`afcon360_app` instead of `afcon360-user-dev`) | This constitution locks workspace to `C:\Users\OBED\Desktop\afcon360-user-dev` |

---

## 3. Agent Rules — Mandatory

### 3.1 Workspace
```
ALWAYS work in: C:\Users\OBED\Desktop\afcon360-user-dev
NEVER enter:    C:\Users\OBED\Desktop\afcon360_app (or any other directory)
```

### 3.2 Branch Discipline
| Action | Rule |
|--------|------|
| **Current branch** | Must be `reconcile/user-local-files-20261121` |
| **Commits** | Make only on `reconcile/user-local-files-20261121` |
| **Push** | Push only to `origin/reconcile/user-local-files-20261121` |
| **PR target** | Only PR #128 (or its successor) targeting `feat/native-user-app-integration-20261108` |
| **Direct commits to baseline** | **FORBIDDEN** — `feat/native-user-app-integration-20261108` is protected |
| **Merge to baseline** | Only via PR #128 after **all required checks pass** |

### 3.3 Required CI Checks (must pass before PR merge)
| Check Job | Purpose |
|-----------|---------|
| Classify User changes — OTA or native rebuild | Change classification gate |
| Expo dependency and TypeScript checks | Static validation |
| Parse and lint mobile-workspace.yml | Workflow integrity |
| User pre-build backend integration and session-security tests | Backend contract |
| User APK — login, protected journeys, restore and logout | Core E2E (android-17) |
| Build or reuse local-first Metro User development-client APK | Artifact production |
| Qualify Metro, EAS fallback and startup on Android | Delivery qualification |

**Do not require** Android version matrix jobs (android-8.0, 9, 11, 12, 14, 15) — currently failing due to uninstall dialog differences.

### 3.4 Local Changes — Preserve
The working branch has **uncommitted changes** that are part of the development environment:
- **6 modified tracked files** (Metro auto-start, dependency updates, dev menu, etc.)
- **11 untracked files** (Metro scripts, connection screen, launchers, runtime state)

**Agents must never:**
- `git restore`, `git reset`, `git clean`, or `git stash` these files
- Delete or rename Metro/launcher scripts
- Commit them indiscriminately without review

### 3.5 Metro Development Environment
The local workspace runs a **live Metro + Flask + ADB reverse tunnel** stack:
- `metro_status.json` → `"status": "running", "port": 8081`
- `metro_trigger.json` → start trigger
- `start-all.ps1` / `start-all.bat` → orchestrators
- `launch-usb-dev.ps1` → USB ADB reverse + deep link

**Agents must not stop or disrupt** these services.

---

## 4. Current State (2026-11-23)

| Item | Status |
|------|--------|
| Local HEAD | `5f094a56` (aligned with `origin/reconcile/user-local-files-20261121`) |
| PR #128 | Open, draft, **MERGEABLE** — Android journey test in progress |
| Required checks | 7/7 passing (android-17); Android matrix partially failing |
| Backup | `C:\Users\OBED\Desktop\afcon360-user-dev-backup-20261123-140555` |

---

## 5. Agent Workflow — Standard Loop

```
1. cd C:\Users\OBED\Desktop\afcon360-user-dev
2. git status                     # Verify branch + local changes
3. Do authorized work on reconcile/user-local-files-20261121
4. git add <specific files>       # Never 'git add .' blindly
5. git commit -m "type(scope): message"
6. git push origin reconcile/user-local-files-20261121
7. Verify PR #128 checks pass
8. Merge PR #128 only when ALL required checks green
```

---

## 6. Escalation

| Situation | Action |
|-----------|--------|
| Unsure about branch/commit | **STOP** — ask human |
| CI check failing unexpectedly | Report exact job + logs; do not force merge |
| Need to change baseline rules | Human decision required |
| Local Metro/Flask broken | Report; do not `git clean` |

---

## 7. Quick Reference

| Command | Purpose |
|---------|---------|
| `git branch --show-current` | Confirm on `reconcile/user-local-files-20261121` |
| `git status --short` | See 6 modified + 11 untracked (expected) |
| `gh pr view 128 --repo twikirize/afcon360 --json statusCheckRollup` | Check PR gates |
| `cat metro_status.json` | Verify Metro running |

---

**This constitution is binding.** Agents that violate it will be corrected. The human owns branch governance; agents execute within these boundaries.

*End of Document*