# AFCON360 — Agent Directive

**Every agent, every task, every session. No exceptions.**

You are working on AFCON360. The system is built deliberately.
Understanding comes before code. Proof comes before closure.

---

## 1. The Method — EGGE

Every work item runs:

UNDERSTAND → MAP → TRACE → PROVE → MINIMAL CHANGE → VERIFY → GATE → RECORD → NEXT

text

No step skipped. No step reordered. If a step cannot be completed,
the work item is BLOCKED, not PASS. Partial is BLOCKED.

**Read first, in this order, before responding to any task:**
1. `AGENTS.md` (this file)
2. `docs/transport/02-OPERATING-SYSTEM.md` (the operating system)
3. The work item's contract file: `docs/transport/nodes/<node-id>-contract.md`

---

## 2. What You Produce

Every work item produces exactly three files:

1. `docs/transport/nodes/<node-id>-contract.md` — written by the human, before any code
2. `docs/transport/nodes/<node-id>-evidence.md` — written by the agent, after the human confirms PASS
3. `docs/transport/nodes/<node-id>-record.md` — written by the agent, after the human confirms PASS

The register is the HUMAN's step. The agent never writes the register.

---

## 3. The Final Report Block

Every session ends with a Final Report block, in this exact shape, in your last message (or the final message of the node):

```markdown
STATUS: PASS | FAIL | BLOCKED | DEFERRED
NODE: <node-id>
SCOPE: <node-id scope>
PHASE: PLANNING | IMPLEMENTATION | PROOF
COMMIT: <sha> | none
REGISTER: <DOC-201-S / DOC-202-S row updated?> | unchanged
FILES CHANGED:
  - <path/to/file>   (+12 -4)
BEHAVIOR: <one sentence>
VERIFICATION: <commands + outcomes>
RESIDUAL RISK: <one honest paragraph> | none
FOLLOW-UPS: <list> | none
GATE: <PASS | FAIL | BLOCKED | DEFERRED>
```

---

## 4. Enforcement

The gate is the proof. The register is the truth. The handoff is the evidence. The contract is the human's intent. **The agent never writes the register.**

---

## 5. The Red Lines

You may NOT, under any circumstances:

- Run or generate migrations without documented human approval in the contract.
- Modify wallet code (`app/wallet/**`) or KYC code without explicit authorization in the contract.
- Modify shared test fixtures (`tests/conftest.py`, `tests/setup_owner.py`) unless the contract explicitly authorizes it.
- Touch `app/models/base.py`.
- Reopen a closed node.
- Inline a new pattern instead of using the established one.
- Invent an alternative to a documented rule.
- "While we're here" additions. Record in Follow-ups and move on.
- Let a "while we're here" addition to the OS be the exception to this rule.
- Non-green tests. Only judged against the human-confirmed acceptance criteria.
- Judge from memory. Facts first, line numbers, actual code.

---

## 6. What Changed and Why

This file replaces the old AGENTS.md, a 2,626-line constitution that:
- was read by almost nobody
- gave agents the raw material to *hide behind* — "I can't be expected to read 2,626 lines"

The constitution is not deleted; every past version is recoverable from git. Historical versions of the constitution are recoverable from git. Run `git log --oneline -- .opencode/rules/afcon360-constitution.md` to see the change history; run `git show <commit>:.opencode/rules/afcon360-constitution.md` to read the exact rules in effect at that commit. Each commit message records what changed and why. No separate archive file is maintained.

Why this file exists:
- The old constitution was written for a system that did not yet have a working realization.
- The Operating System is written for the system that exists now.
- Agents need a small file that is actually read, not a large file that is admired.

The rules that matter are short. The OS is long on purpose: every node enforces it.

---

## 7. Multi-Agent Tooling Policy

We have multiple coding agents working on this repository, including OpenCode agents/subagents, Junie, and potentially other IDE/CLI coding agents.

The repository must therefore have a **shared tooling-awareness policy**, rather than relying on one agent remembering which tools exist.

### 7.1 Shared Rule

Update the appropriate project-level agent guidance so that coding agents are instructed:

> Before starting a workstream, discover and use relevant installed tooling/MCP capabilities when they materially improve investigation, execution, browser verification, JSON/API inspection, database inspection, debugging, or evidence collection.

The rule is:

**Discover first → use when materially useful → do not install unnecessarily.**

MCP/tool availability does not change engineering governance.

### 7.2 Playwright MCP

Record explicitly that **Playwright MCP is installed and available** in the AFCON360 development environment.

Agents capable of using it should use it for appropriate tasks such as:

```text
real browser navigation
real UI interaction
visual verification
form submission
JavaScript behavior investigation
network/request inspection
JSON/API response inspection
browser console inspection
gelocation testing
session/authentication behavior
responsive/UI verification
end-to-end evidence collection
```

Do not substitute static HTML inspection when a real browser check is materially required.

Do not assume Playwright MCP is unavailable without checking.

### 7.3 Other MCPs

There are additional MCP capabilities available in the development environment.

Agents must not assume:

> "I don't have that capability."

without first checking whether an installed MCP/tool provides it.

Examples of potentially useful capabilities include:

```text
browser/UI investigation
GitHub/repository operations
filesystem/document retrieval
database/data inspection
external-service integrations
design/prototype inspection
other environment-specific tools
```

Only use a tool when it materially helps the active workstream.

Do NOT call every MCP just because it exists.

Large MCP tool inventories add context and can make agents less effective, so agents should select only the MCPs relevant to the current node. This is consistent with OpenCode's own guidance that MCP servers add context and should be enabled/used carefully.

### 7.4 Playwright MCP vs Playwright Test

These are different and both are valid.

#### Playwright MCP

Use for:

* interactive browser investigation;
* live debugging;
* visual inspection;
* exploratory journeys;
* controlled browser evidence.

#### Playwright Test

Use for:

* repeatable automated regression;
* committed `.spec.*` tests;
* CI/test-suite execution;
* permanent regression protection.

Do NOT treat Playwright Test as a replacement for Playwright MCP.

Do NOT treat Playwright MCP interactive success as automatically equivalent to a committed automated regression test when the node specifically requires repeatable automation.

### 7.5 Agent-Specific Tool Access

The project instructions must make agents aware that tool availability depends on the agent host/configuration.

#### OpenCode

OpenCode supports:

* primary agents;
* subagents;
* project agents under `.opencode/agents/`;
* project rules through `AGENTS.md`;
* MCP servers configured in OpenCode.

For every AFCON360 OpenCode agent/subagent that has browser/tool access, include the MCP-awareness rule in its operating instructions.

Do not assume that because the main agent has a tool, every subagent automatically has identical permissions. The agent configuration must be checked.

#### Junie

Junie consumes project guidance through:

```text
.junie/AGENTS.md
or
AGENTS.md + .junie/playbook.md + .junie/rules/*.md
```

and supports MCP servers through its MCP configuration.

Ensure the AFCON360 project guidance tells Junie to use relevant MCP capabilities when available, especially browser verification.

If `.junie/AGENTS.md` exists, account for its precedence rather than assuming the root `AGENTS.md` is automatically combined.

### 7.6 Other Coding Agents

For other coding agents/IDEs such as JetBrains-based agents or future agent integrations:

* preserve the shared AFCON360 engineering policy in root `AGENTS.md`;
* where the agent has its own project-specific instruction file, add a corresponding MCP/tool-awareness rule there;
* do not duplicate large architecture documents unnecessarily;
* point agents back to the canonical project instructions.

The objective is:

```text
one engineering governance source
+
agent-specific tool availability
+
MCP discovery when useful
```

not multiple conflicting rulebooks.

### 7.7 Do Not Install MCPs or Packages Automatically

Tool discovery does NOT authorize installation.

When an agent finds that a required capability is missing:

```text
TRACE
→ identify the smallest setup
→ report dependency/change impact
→ obtain required approval
→ install/setup
→ verify
```

Do not silently install:

* MCP servers;
* npm packages;
* Python packages;
* browser tooling;
* database tools;
* external services.

### 7.8 AFCON360 Governance Still Overrides Tooling

MCP availability never overrides:

**UNDERSTAND → MAP → TRACE → PROVE → MINIMAL CHANGE → VERIFY → GATE → RECORD → NEXT**

Agents must still:

* establish source truth before edits;
* establish ownership before changing code;
* prove behavior before claiming completion;
* preserve closed nodes;
* avoid unrelated work;
* avoid migrations unless authorized;
* avoid production commands;
* report evidence rather than assumptions.

## 8. Browser Automation and Local Ports

When browser verification is required, agents MUST use **both** available browser automation options:

1. **Playwright MCP** — configured and available in the development environment (`.playwright-mcp/`). Use for interactive investigation, live debugging, visual inspection, exploratory journeys, and controlled browser evidence collection.
2. **Playwright Test** — configured via `playwright.config.js` (test runner at `tests/browser/`). Use for repeatable automated regression, committed `.spec.*` tests, CI/test-suite execution, and permanent regression protection.

**Never claim one was used when it was not.** Do not substitute static HTML inspection when a real browser check is materially required.

### Preferred Local Ports

Reuse the existing development setup rather than inventing new ports or launching duplicate servers:

- **HTTPS development server: port 5443** — uses the development CA in `certs/` for TLS. Do not disable TLS verification.
- **Local HTTP test server: port 500** — where supported by the task and repository configuration.
- **Playwright D3 test server: port 5611** — defined in `playwright.config.js` (`D3_TEST_PORT`), serves the real app via `tests/browser/start_test_server.py` with `TestingConfig` against the isolated `*_test` database.

### Verify the Target Before Acting

- Establish the host, protocol, application configuration, and database target **before** performing state-changing browser actions.
- Never assume two ports use the same database.
- Use an **isolated test database** for test bookings and other mutations; never use production or shared real-user data for test evidence.

### Preserve Security

- Use the existing development CA for HTTPS (in `certs/`).
- Do not disable TLS verification, expose credentials, or bypass authentication/authorization to make a browser test pass.

### Collect Verifiable Evidence

When relevant, preserve:
- Screenshots or traces
- Browser console/network errors
- Server logs
- Test commands, exit codes, and corresponding backend/database outcomes

### Respect Task Scope

Browser tools **supplement**—not replace—source tracing and automated tests. Do not run state-changing journeys, change code, restart services, or alter configuration unless the active task explicitly authorizes them.

---

## 9. Database Credentials & Password Verification (pgpass — Permanent Rule)

**Applies to every agent, every database-related task. The libpq pgpass file is the ONLY place a PostgreSQL password may exist.**

### 9.1 The credential model

- Password store: `%APPDATA%\postgresql\pgpass.conf` (Windows) / `$HOME/.pgpass` (Linux/macOS, mode 0600), ACL restricted to the owning account (`icacls <file> /inheritance:r /grant:r "%USERNAME%:(R,W)"`).
- Format `hostname:port:database:username:password`, first match wins — specific entries go above `*` wildcards. The host field must match the connection host string exactly: `localhost`, `127.0.0.1`, `::1`, and a docker service name like `db` are different keys.
- Every DSN in this repo is **passwordless by design**: `postgresql://user@host:port/db`. libpq falls back to pgpass. `DATABASE_URL`, `TEST_DATABASE_URL`, `DB_PASS`, `APP_DB_PASS` never carry a password.

### 9.2 Never (credential red lines)

- Never place a DB password in: `.env*` files, any URL, `PGPASSWORD` (any scope), a command line, a script, a test fixture, source code, logs, error messages, evidence files, or chat.
- Never print a URL that might carry credentials. Redact: `re.sub(r'(://[^:]+:)[^@]+(@)', r'\1***\2', url)`.
- Never "fix" a DB auth failure by putting a password back into env/URL/config — fix the pgpass entry (path, format, ACL, host field). Reintroducing a password violates §5.
- Never write the password value yourself, not even into pgpass. Credential creation and rotation are human operations: give the operator the exact commands; they supply the secret.

### 9.3 Verification protocol (run before claiming any DB-related result)

Report commands and exit codes only — never values:

1. **No secret in scope** — `$env:PGPASSWORD` empty; User and Machine scope `PGPASSWORD` empty.
2. **Auth** — `psql -w -U <user> -h <host> -d <db> -t -c "select 1"` → exit 0 proves pgpass works. `-w` never prompts, so no password can reach shell history. On failure the error names the pgpass file that matched — fix that file, never the URL.
3. **App boot** — `python -c "from app import create_app; create_app(); print('DB_VERIFY_OK')"` → exit 0, and assert `SQLALCHEMY_DATABASE_URI` contains no `user:pass@` pair.
4. **Tests** — `TEST_DATABASE_URL` passwordless; run the targeted pytest (`tests/postgres_contract.py` enforces migration-built PostgreSQL).
5. **Subprocess tools** (`pg_dump`/`psql`/`pg_isready`) inherit pgpass — never export `PGPASSWORD` (pattern: `app/backup/backup_service.py:_db_env` skips it when empty).
6. **Containers/remote hosts** do NOT read this machine's pgpass — they need their own file (BACKLOG DB-PGPASS-01). There: BLOCKED + record; do not fall back to env passwords.

**A DB claim without exit-0 evidence from steps 1–4 is BLOCKED, not PASS.**

### 9.4 Evidence to include in reports

pgpass path used, entry count (never contents), ACL, probe commands with exit codes, redacted URI. Full triage table for auth failures: `.opencode/rules/afcon360-constitution.md` §49.

---

## 10. Production Cutover, Backups & Rollback (Permanent Rule)

**Applies to every agent, every database-reliability task. This section is a record and a rule set. It authorizes no cutover, rollback, migration, restore, or database mutation.**

### 10.1 Recorded production state (25 October 2026; M3 update 26 October 2026)

| Role | Database | Alembic revision | Verified facts |
|---|---|---|---|
| Current production | `afcon360_prod` | `1793013676` | 109 users, 61 transport bookings, `ck_pickup_time_sane` present; `ck_pickup_time_mode_aware` corrected and validated (M3, 26 Oct 2026) |
| Preserved previous production — rollback resource | `afcon360_prod_old` | `df55cbe3f516` | Pre-rename checks recorded 109 users and 61 bookings |

- Revision history: `1792869659` → `1793011323` (M2) → `1793013676` (M3, corrected `ck_pickup_time_mode_aware`). M1/M2 remain applied; do not roll back production to `1792869659`.
- `afcon360_prod_old` is the rollback resource. It must not be dropped, overwritten, upgraded, or repurposed as part of any documentation, cleanup, or reliability task.
- `afcon360_h3_candidate_cutover_test` (the old Gate 4 candidate) contains **test data** and must never be promoted to production.
- The clean candidate was upgraded and populated **before** being renamed to `afcon360_prod`. Do not imply the old Gate 4 candidate was used for the final promotion.

### 10.2 Recovery points (outside the repository)

| Archive | Path | Size | Verification status |
|---|---|---|---|
| Pre-cutover | `C:\Users\OBED\AppData\Local\AFCON360\rebuild-evidence\afcon360_prod_pre_cutover_20261025_160251.dump` | 1,670,399 bytes | Previously reported restore-verified; treat as the pre-cutover recovery archive |
| Post-cutover | `C:\Users\OBED\AppData\Local\AFCON360\rebuild-evidence\post_cutover_20261025_201202\afcon360_prod_post_cutover_20261025_201202.dump` | 1,664,542 bytes | `pg_restore -l` successfully read its metadata/TOC — archive readable; a complete restore test has NOT been demonstrated |
| Pre-M3 rehearsal | `C:\Users\OBED\AppData\Local\AFCON360\rebuild-evidence\pre_m3_prod_20261026_143847.dump` | 1,665,589 bytes | Full custom-format dump; restored into isolated `afcon360_p1_candidate`; candidate verified at `1793011323` (109 users, 61 bookings); M3 applied and verified; P1 suite 40/40 on a `_test` clone |
| Pre-M3 final | `C:\Users\OBED\AppData\Local\AFCON360\rebuild-evidence\pre_m3_prod_final_20261026_144843.dump` | 1,665,589 bytes | Full custom-format dump; `pg_restore -l` verified; SHA256 `28D7DF538AD5C360131CE1090729E0EB9B3E6A300721C6E6183CB1C9062FBEA9`; ACL owner-only; final pre-M3 recovery point |

- Archive readability (`pg_restore -l`) is not restore verification. Never describe the post-cutover archive as restore-verified.
- The 14:38 pre-M3 dump was fully restored into `afcon360_p1_candidate`; the 14:48 final pre-M3 dump has `pg_restore -l` verification only. Neither archive is a substitute for an authorized rollback procedure.
- These are Windows paths recorded for one machine. They are not portable and are not guaranteed to exist on another computer.
- Full recovery detail and the rollback runbook: root `README.md` → "Production Database Cutover and Recovery — 25 October 2026".

### 10.3 Operational rules

- Every production database cutover must have a documented pre-cutover recovery point, a post-cutover recovery point, their exact locations, and their verification status.
- Verify the actual database identity and migration revision with read-only checks before issuing any migration or restore command.
- Never assume that a database name, a `.env.local` setting, or a successful command proves the application is connected to the intended database.
- Production rollback is an explicitly authorized operational procedure with precondition checks — never an automatic response. Do not roll back solely because of an unverified warning or a superficial mismatch; investigate first and retain evidence.
- Backups, dump files, and credentials remain outside source control. Never commit `.env.local`, `.env.local.pre_cutover`, dump archives, or credential-bearing files. `.env.local.pre_cutover` is a configuration snapshot only; its database name must be re-checked before any rollback use.
- `afcon360_p1_candidate` is an isolated rehearsal copy of production (restored at `1793011323`, M3 applied and verified). It must not be used by application services, scheduled jobs, notifications, or external integrations, and must not be promoted to production.
- Any future agent performing database-reliability work must read the documented recovery information in `README.md` before proposing operations that could affect production data.

---

## 48. Model Defaults & Migration Safety (Permanent Engineering Rule)

**Applies to every agent, every future model, and every database change in AFCON360.**

### 1. Inspect before adding or changing model fields

Before adding or changing a SQLAlchemy model, column, Python default, server default, enum, nullability rule, or constraint:

- Inspect the existing model, its imports, relationships, defaults, constraints, and all relevant write paths.
- Establish whether the table and column already exist in the target databases.
- Determine whether existing rows are present and whether they satisfy the proposed new constraints.
- Inspect the actual database column type, nullability, server default, indexes, constraints, and enum labels where relevant.
- Check both production and test database schemas. Matching Alembic revision numbers do not, by themselves, prove the schemas are identical.
- Preserve existing data, existing contracts, and unrelated working-tree changes.

**Never assume that a model declaration accurately describes every existing database.**

### 2. Distinguish Python defaults from database defaults

Agents must understand and explicitly account for these differences:

- **`default=`** is a SQLAlchemy-side default. It is normally applied when SQLAlchemy issues an insert without a supplied value; it is not a general database default for raw SQL or other database clients.
- **`server_default=`** defines a database-side default used when an insert omits the column and the database applies that default.
- **No default** means the application or database must supply a value when the column and its constraints require one.

A Python-side default does not automatically backfill existing records or establish a database default. Do not assume that changing `default=` will generate a database migration.

For every new or changed default, state which behavior is required: ORM insert behavior, database-wide insert behavior, or both. Implement only the behavior justified by the existing application and database contract.

### 3. Special rules for existing tables and populated columns

Never introduce a migration that assumes a table is empty or that existing records already have the new field populated.

Before adding a column or tightening nullability:

- Determine how existing rows will obtain valid values.
- Verify that the selected default is valid for the actual database type and constraints.
- Assess whether a `NOT NULL`, unique, foreign-key, check, or enum constraint will reject existing data.
- Consider the safety of the migration on a populated production table, including locking, table size, and potential data loss.
- Distinguish a temporary migration/backfill requirement from the application's long-term default behavior.

Do not add a required column without proving that existing rows can satisfy the new requirement. Do not silently invent a backfill value, overwrite existing data, or make an existing field nullable merely to get a migration to pass.

If the safe migration path cannot be established under the repository's approved migration workflow, **STOP and report BLOCKED** with the evidence and the decision required.

### 4. PostgreSQL enums require exact compatibility

Before restoring or introducing native PostgreSQL enum columns:

- Verify the PostgreSQL type name and actual labels in each relevant database.
- Compare the labels with the Python enum's member names and member values.
- Explicitly select name-based or value-based persistence. Use `values_callable` only when the proven database labels require enum values rather than member names.
- Ensure Python defaults and server defaults use valid persisted enum labels.
- Inspect existing string assignments, comparisons, serialization, and API/service write paths that may break when a column starts returning enum members rather than plain strings.
- Do not assume that a matching Alembic revision means the enum types or schemas match.
- Use `create_type=False` only when the referenced PostgreSQL type is confirmed to exist and the provisioning strategy accounts for its creation elsewhere.

Never repair an enum mismatch by guessing, renaming labels, changing shared enum contracts, or altering live PostgreSQL types without authorization.

### 5. Migration governance is mandatory

**A. Ordinary incremental schema changes — strict default**

- Schema changes must originate from the authorized canonical source, including models, metadata registration and configuration as applicable.
- Use Flask-Migrate/Alembic autogeneration (`flask db migrate`) to generate ordinary migration files.
- Inspect the generated migration for completeness and unintended operations before upgrading.
- Agents MUST NOT manually create, patch, reorder or repair ordinary generated migration files to compensate for missing or incorrect autogeneration.
- If changes are missing or wrong, STOP. Correct the underlying source, metadata registration or autogeneration configuration, then discard and regenerate the defective, not-yet-applied candidate as permitted by the repository's governance.
- Never edit an already-applied historical migration casually to make current code or tests pass.
- Never use manual DDL, `stamp`, or another shortcut to conceal uncertainty about the schema or revision state.
- A successful migration or passing test does not independently prove that the intended schema change was captured correctly.
- Apply the reviewed migration through the authorized Alembic upgrade process.
- Never use `db.create_all()` as a substitute for the authoritative migration path on a non-test installation.
- No production migration, schema modification or data-changing operation without the required authorization.

These requirements are permanent for ordinary schema changes and must not be weakened by an exception.

**B. One-time baseline replacement exception**

A one-time, explicitly owner-authorized migration-baseline reconstruction or history-squash operation may follow the narrow process defined in subsection 8 of this section. That exception applies only to its named scope and deliverables. It does not permit hand-patching ordinary forward migrations or bypassing autogeneration when an ordinary schema change is incompletely detected.

**C. Mandatory decision rules**

- Ordinary schema change → correct the canonical source, regenerate via Alembic, inspect the complete result, then follow the authorized upgrade process.
- Authorized one-time baseline reconstruction → follow subsection 8 and its additional review and transition gates.
- Incomplete autogeneration → STOP and fix the source/configuration; do not patch the generated migration.
- Unknown or divergent existing database state → STOP and collect authorized evidence; do not stamp or alter the database to make it appear consistent.

### 6. Prove model and database behavior

Where changes are authorized, verification should distinguish:

1. ORM inserts that omit the field.
2. Direct database inserts that omit the field, where database-default behavior is required.
3. Existing rows during the migration.
4. Explicitly supplied values and invalid values.
5. Fresh test-schema creation versus migration-upgraded schema behavior.
6. Production/test differences that could change the outcome.

Use the repository's approved tests and read-only database probes before any write operation. Do not claim a migration is safe solely because model imports succeed or unit tests pass.

### 7. Required evidence before implementation

For every model/default/migration change, report:

- The table and column affected.
- Whether the table and column already exist in each relevant database.
- Existing nullability, type, default, constraints, enum labels, and relevant data conditions.
- The intended Python-side and database-side default behavior.
- The existing-row and migration strategy.
- The affected application write paths and compatibility tests.
- The proposed migration impact and any unresolved risk.

Classify the gate as **PASS**, **FAIL**, **BLOCKED**, or **DEFERRED** using the project governance rules. Do not mark PASS while a material compatibility or data-safety question remains unresolved.

### 8. One-time authorized baseline reconstruction (H3/N-squash)

A deliberately authorized baseline reconstruction or migration-history squash, such as the selected H3/N-squash, is not an ordinary incremental schema change. It is permitted only for a specifically named, owner-authorized operation and its defined deliverables.

- The operation must have an explicit owner-approved scope, responsible owner, independent review requirements, supported starting-state policy, and transition/recovery plan before implementation.
- The produced baseline must be deterministic, version-controlled, independently reviewable, and reproducible from an empty disposable PostgreSQL database.
- The authoritative H3 baseline must not dynamically derive schema from whatever application models are imported at runtime. It must not use `db.metadata.create_all()` or `drop_all()` as a substitute for a frozen migration definition.
- Existing databases must have evidence-backed starting-state classifications and reviewed transition handling. A revision identifier alone is not proof of physical schema parity.
- Disposable verification databases may be created or recreated only under the approved test procedure. This does not authorize resetting, dropping, stamping, or modifying production or other protected databases.
- Actual application schema transitions remain under the reviewed Alembic migration path. A model-bootstrap/reset script is not a substitute for the authoritative migration chain.
- Production or other existing-database cutover requires separate explicit authorization. Preparing or reviewing the baseline does not authorize cutover.
- The exception does not authorize routine migration patching, concealment of autogeneration defects, or a precedent for ordinary future model changes.
- H3 implementation and cutover remain subject to the reliability register's open readiness gates; selecting the architecture is not cutover approval.

**Governing principle:** A model declaration is not migration proof. Every new field, default, enum, and constraint must be compatible with both future writes and the database state that already exists.

---

*End of Directive. Begin with UNDERSTAND.*