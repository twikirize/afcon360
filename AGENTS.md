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

*End of Directive. Begin with UNDERSTAND.*