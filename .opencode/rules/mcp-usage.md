# OpenCode MCP Usage Guide

**This file documents the available MCP servers for OpenCode agents and how/when to use them.**
**MCP servers are capabilities, not authority. AFCON360 architecture, ownership rules, EGGE, protected files,
and explicit authorization remain always authoritative.**

---

## Available MCP Servers

The following MCP servers are configured and available for OpenCode agents:

### 1. `afcon360-files` — Primary Project/Repository Inspection

- **Status:** ENABLED
- **Purpose:** Controlled filesystem access to the AFCON360 project directory
- **Root:** `C:\Users\OBED\Desktop\afcon360_app`
- **Use for:**
  - Inspecting source files, tests, templates, configuration, documentation
  - Editing authorized files within the project
  - Inspecting project structure and file relationships
- **Do NOT expand to:** `C:\`, user home directory, Desktop, Documents, SSH directories, unrelated projects
- **Security principle:** Filesystem access must remain project-scoped
- **EGGE relevance:** TRACE → PROVE → VERIFY → RECORD

> **Agents should select this automatically** for any task involving file inspection, modification, or project structure analysis. No need to explicitly mention MCP on every task.

### 2. `playwright` — Browser/UI/E2E Verification

- **Status:** ENABLED
- **Purpose:** Real browser automation for UI and E2E verification
- **Use for:**
  - Opening the local AFCON360 application
  - Testing forms, onboarding, login, dashboards
  - Checking rendered pages and UI regression
  - Browser-based workflows and visual verification
  - HTTP/E2E tests, onboarding, identity context, accommodation flows, payment UI, wallet UI
- **Typical target:** `localhost` development/test application
- **Do NOT use** as a production browser automation channel without explicit authorization
- **EGGE relevance:** VERIFY → GATE

> **Agents should select this automatically** when task involves real browser, UI, session, form, onboarding, or E2E evidence.
> Browser testing must target the **local AFCON360 application** unless production access is explicitly authorized.
> Some times test in the report if it says it can see them and use them.

### 3. `context7` — Authoritative Framework/Library Documentation

- **Status:** ENABLED
- **Purpose:** Retrieve current, version-aware technical documentation
- **Useful for:** Flask, Python, SQLAlchemy, Flask-Migrate, Alembic, PostgreSQL, Redis, Celery, pytest,
  WTForms, Flask-Login, Playwright, and other libraries used by AFCON360
- **Correct order:**
  1. Understand AFCON360 implementation
  2. Identify applicable library behavior
  3. Consult current documentation when needed
  4. Compare documentation with actual implementation
  5. Make the smallest authorized change
- **Important:** Context7 provides documentation knowledge. It does NOT replace reading the actual AFCON360 codebase.
- **EGGE relevance:** VERIFY → GATE

> **Use when authoritative/current framework or library documentation is needed.** Do not use as a substitute for
> inspecting the actual codebase.

### 4. `afcon360-git` — Git Repository Inspection

- **Status:** ENABLED
- **Purpose:** Structured access to the local Git repository
- **Use for:** git status, history, branches, commits, diffs, repository inspection, tracing when a change was
  introduced, evidence gathering
- **EGGE relevance:** TRACE → PROVE → VERIFY → RECORD
- **Must never be treated as permission to:** rewrite history, force-push, destroy branches, reset user work,
  discard uncommitted changes

### 5. `github` — GitHub Integration

- **Status:** ENABLED
- **Purpose:** Connect OpenCode to the GitHub repository and GitHub services
- **Use for:** repository inspection, issues, pull requests, commits, Actions, CI investigation, security
  information where authorized, project collaboration
- **Authentication:** `GITHUB_PERSONAL_ACCESS_TOKEN` must be supplied through an environment variable
- **Never:** hard-code the token into opencode.json, place secrets into source control, expose GitHub
  credentials to unrelated MCP servers

---

## MCP Usage Guidelines

### Selecting the Appropriate MCP

- **Agents should select the appropriate MCP automatically** based on the task — they do not need the user
  to explicitly mention MCP on every task.
- Start with `afcon360-files` for project inspection, then use other MCPs as needed for the specific
  evidence or capability required.

### When to Use Each MCP

| Task Type | Primary MCP |
|-----------|-------------|
| File inspection/edit | `afcon360-files` |
| Browser/UI/E2E verification | `playwright` |
| Framework/library docs | `context7` |
| Git operations | `afcon360-git` |
| GitHub issues/PRs | `github` |

### MCP Are Capabilities, Not Authority

> **MCPs are capabilities, not authority.** Having an MCP tool available does NOT mean the agent is
> authorized to use it for any purpose. Authorization still comes from:
>
> 1. Explicit user instruction
> 2. Approved specifications / ADRs / contracts
> 3. AGENTS.md / AFCON360 Constitution
> 4. Graph-node task scope
> 5. Module ownership rules
> 6. Security rules

### Never Use Every MCP Unnecessarily

- Only enable/use the MCP(s) required for the task
- Using multiple MCPs unnecessarily adds context overhead and security exposure
- The goal is **maximum useful capability with minimum unnecessary context and minimum security exposure**

### Browser Testing Requirements

- **Browser testing must target the local AFCON360 application** unless production access is explicitly authorized
- Playwright is for development/test verification, not production automation
- Any production browser automation requires explicit user authorization

### Documentation and Reporting

- When using MCP browsers (Playwright), include verification evidence in the post-change report
- Report what MCP was used, for what purpose, and the results
- If the report says the agent can see browser elements and use them, document this in the verification section

---

## EGGE Integration (Every MCP-assisted task)

```
UNDERSTAND → MAP → TRACE → PROVE → MINIMAL CHANGE → VERIFY → GATE → RECORD → NEXT
```

- **MCP tools are evidence sources** — they do not replace the engineering loop
- Follow the full EGGE loop for every task, using MCPs as evidence-gathering tools where appropriate
- Record deferred work in BACKLOG.md (§11) if relevant
- Produce evidence-based completion report (§39)

---

## Enablement Policy (from MCP-STACK.md §21)

**Essential (always available):**
- `afcon360-files`
- `afcon360-git`
- `github`
- `playwright`
- `context7`

**Disabled until needed:** `postgres-test`, `fetch`, `memory`, `sequential-thinking`, `mcp-everything`,
`time`, `sentry`, `oracle-cloud`, `cloudflare`, `afcon360`

> **Future setup agents MUST NOT enable a disabled server simply because a task mentions it.**
> They must first determine:
> 1. Why it is needed
> 2. What data it can access
> 3. What authority it gives
> 4. Whether a lower-risk existing tool already solves the problem
> 5. Whether the user has authorized activation

---

## References

- **MCP-STACK.md** (`C:\Users\OBED\Desktop\afcon360_app\.opencode\MCP-STACK.md`) — Detailed per-server
  configuration, security boundaries, and enablement policy
- **AGENTS.md** (`C:\Users\OBED\Desktop\afcon360_app\AGENTS.md`) — Constitution and EGGE loop
- **opencode.json** (`C:\Users\OBED\Desktop\afcon360_app\opencode.json`) — MCP server configuration