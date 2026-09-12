# AFCON360 MCP STACK

## Purpose

This document defines the intended MCP architecture for AFCON360.

MCP servers are capability connectors for the AI coding agent.

They do NOT override:

1. Explicit user instruction
2. Approved specifications / ADRs / contracts
3. AGENTS.md / AFCON360 Constitution
4. Graph-node task scope
5. Module/domain rules
6. Workflows / skills
7. MCP/tool instructions
8. Existing implementation
9. Existing tests
10. Agent inference

MCP access must therefore remain subordinate to the AFCON360 constitution and the Evidence-Gated Graph Engineering (EGGE) loop.

EGGE:

UNDERSTAND
→ MAP
→ TRACE
→ PROVE
→ MINIMAL CHANGE
→ VERIFY
→ GATE
→ RECORD
→ NEXT


# 1. AFCON360 FILESYSTEM

Name:

afcon360-files

Status:

ENABLED

Purpose:

Provide controlled filesystem access to the AFCON360 project.

Current root:

C:\Users\OBED\Desktop\afcon360_app

Allowed purpose:

- inspect source files
- inspect tests
- inspect templates
- inspect configuration
- inspect project documentation
- edit authorized files
- inspect project structure

Do NOT expand this server to:

- C:\
- user home directory
- Desktop generally
- Documents generally
- SSH directories
- credential directories
- unrelated projects

Security principle:

Filesystem access must remain project-scoped.

This is one of the essential MCP servers.


# 2. LOCAL GIT

Name:

afcon360-git

Status:

ENABLED

Package:

mcp-server-git

Purpose:

Give the agent structured access to the local Git repository.

Repository:

C:\Users\OBED\Desktop\afcon360_app

Use for:

- git status
- history
- branches
- commits
- diffs
- repository inspection
- tracing when a change was introduced
- evidence gathering

EGGE relevance:

TRACE
PROVE
VERIFY
RECORD

The Git MCP must never be treated as permission to:

- rewrite history
- force-push
- destroy branches
- reset user work
- discard uncommitted changes

Those actions require explicit authorization.


# 3. GITHUB

Name:

github

Status:

ENABLED

Purpose:

Connect OpenCode to the GitHub repository and GitHub services.

Use for:

- repository inspection
- issues
- pull requests
- commits
- Actions
- CI investigation
- security information where authorized
- project collaboration

Authentication:

GITHUB_PERSONAL_ACCESS_TOKEN

The token must be supplied through an environment variable.

NEVER:

- hard-code the token into opencode.json
- place secrets into source control
- expose GitHub credentials to unrelated MCP servers

Because GitHub MCP exposes many tools, keep its tool surface controlled if context usage becomes excessive.

Official server:

GitHub's official GitHub MCP server.

Current remote endpoint:

https://api.githubcopilot.com/mcp/


# 4. PLAYWRIGHT

Name:

playwright

Status:

ENABLED

Purpose:

Browser/UI/E2E verification.

Use for:

- opening the local application
- testing forms
- testing onboarding
- testing login
- testing dashboards
- checking rendered pages
- browser-based workflows
- UI regression investigation
- visual/browser verification

Typical target:

localhost development/test application.

Do NOT use this as a production browser automation channel without explicit authorization.

Playwright is especially important for:

- HTTP/E2E tests
- onboarding
- identity context
- accommodation flows
- payment UI
- wallet UI
- browser regression verification

EGGE relevance:

VERIFY
GATE


# 5. CONTEXT7

Name:

context7

Status:

ENABLED

Purpose:

Retrieve current, version-aware technical documentation.

Useful for:

- Flask
- Python
- SQLAlchemy
- Flask-Migrate
- Alembic
- PostgreSQL
- Redis
- Celery
- pytest
- WTForms
- Flask-Login
- Playwright
- other libraries used by AFCON360

Important:

Context7 provides documentation knowledge.

It does NOT replace reading the actual AFCON360 codebase.

Correct order:

1. Understand AFCON360 implementation
2. Identify applicable library behavior
3. Consult current documentation when needed
4. Compare documentation with actual implementation
5. Make the smallest authorized change

Current remote endpoint:

https://mcp.context7.com/mcp

API key:

Optional for basic use.

If an API key is later added:

Use:

CONTEXT7_API_KEY

Never hard-code the secret.


# 6. POSTGRES TEST

Name:

postgres-test

Status:

DISABLED

Purpose:

Provide structured database inspection for AFCON360 automated testing.

TARGET:

afcon360_test ONLY.

NEVER:

afcon360_prod.

This MCP must NOT be enabled until a currently maintained PostgreSQL MCP implementation has been verified.

Placeholder:

<POSTGRES_TEST_MCP_COMMAND>

Future setup must determine:

1. Current maintained PostgreSQL MCP implementation
2. Exact package/repository
3. Authentication method
4. Connection method
5. Whether read-only mode is available
6. Whether database selection can be hard-bound
7. Whether write access can be disabled
8. Whether the server can be restricted to localhost
9. Whether credentials can be supplied through environment variables

Required safety boundary:

AFCON360 production database MUST NOT be exposed to the AI agent through MCP.

Especially protected:

- wallet data
- financial transactions
- KYC data
- identity data
- production users
- payment information
- audit records

The test database may be used for:

- schema inspection
- constraints
- indexes
- test fixtures
- DB-state verification
- controlled test investigation

No production access.


# 7. FETCH

Name:

fetch

Status:

DISABLED

Purpose:

Retrieve web content and convert it into model-readable content.

Useful for:

- technical documentation
- standards
- public APIs
- public web pages
- research material

Why disabled initially:

OpenCode already has web/search capabilities.

Fetch is therefore supplementary rather than essential.

Enable when:

- direct URL retrieval is needed
- a documentation page cannot be adequately accessed through normal web search
- an agent specifically requires MCP-based page fetching

Current reference package:

mcp-server-fetch

Do not enable merely because it exists.


# 8. MEMORY

Name:

memory

Status:

DISABLED

Purpose:

Knowledge-graph-based persistent MCP memory.

Potential uses:

- technical relationships
- recurring project facts
- long-lived development context

Why disabled initially:

AFCON360 already has authoritative durable sources:

- AGENTS.md
- AFCON360 Constitution
- approved specifications
- ADRs
- BACKLOG.md
- project documentation
- Git history

MCP Memory must NEVER become a competing source of truth.

If enabled later:

Memory remains subordinate to project documentation.

If memory conflicts with an approved AFCON360 specification:

The approved specification wins.


# 9. SEQUENTIAL THINKING

Name:

sequential-thinking

Status:

DISABLED

Purpose:

Structured problem-solving support.

Potential use:

- complex reasoning
- multi-step investigation
- difficult architectural problems

Why disabled:

The AFCON360 agent already follows EGGE.

Adding another reasoning-oriented MCP may add unnecessary context/tool overhead.

Enable only if there is demonstrated value on difficult tasks.


# 10. MCP EVERYTHING

Name:

mcp-everything

Status:

DISABLED

Purpose:

MCP protocol/reference testing.

This is NOT an application-development tool.

Use only for:

- testing MCP functionality
- diagnosing MCP compatibility
- developing/debugging MCP integrations

Never enable during normal AFCON360 development.

It exists as a test/reference server, not as an AFCON360 production capability.


# 11. TIME

Name:

time

Status:

DISABLED

Purpose:

Time and timezone conversion.

Potential uses:

- timezone calculations
- date/time conversion
- event scheduling investigation

Why disabled:

Not essential to current AFCON360 development.

Enable when time-zone-heavy features require dedicated MCP support.

AFCON360 already has normal application-level date/time handling.


# 12. SENTRY

Name:

sentry

Status:

DISABLED

Purpose:

Production/runtime error investigation.

Potential future use:

- production exceptions
- error events
- release diagnostics
- runtime monitoring

DO NOT ENABLE until:

1. Sentry is actually adopted by AFCON360
2. authentication is configured
3. access scope is reviewed
4. production data exposure is understood
5. the user explicitly authorizes production observability access

Never allow Sentry access to become an excuse for modifying production behavior without evidence.


# 13. ORACLE CLOUD

Name:

oracle-cloud

Status:

DISABLED

Purpose:

Future infrastructure management for AFCON360's Oracle Free Tier environment.

Potential future use:

- instance inspection
- deployment diagnostics
- infrastructure status
- logs
- networking

DO NOT ENABLE now.

Reasons:

- infrastructure access is high risk
- production infrastructure should not be directly controlled by an AI agent
- Oracle credentials must remain protected
- deployment must remain explicitly authorized

Future activation requires a separate infrastructure security decision.


# 14. CLOUDFLARE

Name:

cloudflare

Status:

DISABLED

Purpose:

Future DNS/CDN/security/deployment integration.

Potential use:

- DNS
- zones
- CDN
- security configuration
- deployment infrastructure

Do not enable until AFCON360's Cloudflare architecture is finalized and credentials/scopes are deliberately restricted.


# 15. AFCON360 CUSTOM MCP

Name:

afcon360

Status:

DISABLED

Purpose:

Future domain-specific AFCON360 MCP.

This should eventually expose safe, high-level AFCON360 concepts instead of raw database manipulation.

Potential future tools:

- inspect current graph node
- inspect approved contract
- inspect module ownership
- inspect backlog status
- inspect gate status
- verify ownership boundaries
- inspect test evidence
- retrieve architecture metadata
- verify Stage/Node state

It must NOT directly mutate:

- wallet records
- identity records
- organisation records
- accommodation records
- payment records
- production database

The future AFCON360 MCP should therefore become an architectural interface, not a shortcut around the architecture.

This is important because:

NO MODULE MAY DIRECTLY MUTATE ANOTHER MODULE'S RECORDS.

The custom MCP should therefore become an architectural interface, not a shortcut around the architecture.


# 16. SECURITY RULE

MCP access is capability, not authority.

Having an MCP tool does NOT mean the agent is authorized to use it.

Authorization still comes from:

1. User instruction
2. Approved specifications
3. AGENTS.md
4. Graph-node scope
5. Module ownership
6. Security rules


# 17. PRODUCTION DATABASE RULE

ABSOLUTE RULE:

No PostgreSQL MCP may connect to:

afcon360_prod

unless the user explicitly authorizes production database access for a specific task.

Preferred database topology:

OpenCode
    |
    +--> PostgreSQL MCP
             |
             +--> afcon360_test

Never:

OpenCode
    |
    +--> PostgreSQL MCP
             |
             +--> afcon360_prod


# 18. WALLET / FINANCIAL RULE

Wallet is CRITICAL.

MCP must never become a bypass around:

- wallet services
- double-entry accounting
- idempotency
- locking
- ownership checks
- audit trails
- reconciliation
- transaction boundaries

MCP inspection is not permission to mutate financial state.


# 19. IDENTITY / OWNERSHIP RULE

MCP tools must preserve:

internal BigInteger id:
    database/FK use only

public UUID public_id:
    API/URL/external use

Never expose internal IDs through public interfaces.

Never mix:

User IDs
Organisation IDs
Wallet owner IDs
Provider IDs
Event IDs
Accommodation IDs

Ownership must be proven from canonical relationships.


# 20. EGGE INTEGRATION

Every MCP-assisted coding task follows:

UNDERSTAND
→ MAP
→ TRACE
→ PROVE
→ MINIMAL CHANGE
→ VERIFY
→ GATE
→ RECORD
→ NEXT

MCP tools are evidence sources.

They do not replace the engineering loop.


# 21. ENABLEMENT POLICY

Essential now:

- afcon360-files
- afcon360-git
- github
- playwright
- context7

Disabled until needed:

- postgres-test
- fetch
- memory
- sequential-thinking
- mcp-everything
- time
- sentry
- oracle-cloud
- cloudflare
- afcon360

Future setup agents MUST NOT enable a disabled server simply because a task mentions it.

They must first determine:

1. Why it is needed
2. What data it can access
3. What authority it gives
4. Whether a lower-risk existing tool already solves the problem
5. Whether the user has authorized activation


# 22. PLACEHOLDER RULE

Every placeholder in opencode.json represents an intentionally unresolved integration.

A future setup task must replace a placeholder only after verifying:

- current official/maintained implementation
- current package/repository
- current configuration syntax
- authentication method
- security scope
- required environment variables
- whether the integration is actually needed

Do NOT guess package names.

Do NOT use abandoned MCP packages simply because old tutorials mention them.

Do NOT silently replace placeholders.

Record the decision in the project documentation.


# 23. CURRENT TARGET

Current active MCP stack:

1. Filesystem
2. Git
3. GitHub
4. Playwright
5. Context7

Everything else remains intentionally disabled.

This is deliberate.

The goal is not "maximum number of MCP servers."

The goal is:

maximum useful capability
with
minimum unnecessary context
and
minimum security exposure.
Why this version is better

This means a future agent doesn't just see:

postgres-test = false

It sees:

Why is it disabled? What database is allowed? What must be verified before enabling it? What security boundary must never be crossed?

That's exactly what we want for AFCON360.

Also, the PostgreSQL placeholder is intentional. The current official reference inventory identifies Git, Fetch, Filesystem, Memory, Sequential Thinking, Everything and Time, but the old PostgreSQL reference server isn't in that current maintained list. We should therefore make a future agent research and select a maintained PostgreSQL implementation, rather than silently installing an obsolete one.

The same principle applies to Oracle, Cloudflare and Sentry: placeholder now, verified integration later.

Your current active set is therefore only:
🟢 afcon360-files
🟢 afcon360-git
🟢 github
🟢 playwright
🟢 context7

🔴 postgres-test
🔴 fetch
🔴 memory
🔴 sequential-thinking
🔴 mcp-everything
🔴 time
🔴 sentry
🔴 oracle-cloud
🔴 cloudflare
🔴 afcon360

And that gives us a complete future MCP map without prematurely granting the agent access to databases, production infrastructure, or other unnecessary capabilities.