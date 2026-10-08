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

The constitution is NOT deleted. It is preserved verbatim as the historical reference at `docs/transport/reference/CONSTITUTION-ARCHIVE.md`.

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

---

*End of Directive. Begin with UNDERSTAND.*