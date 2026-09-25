# AFCON360 — Operating System

**Status:** AUTHORITATIVE — applies to every agent, every task, every session.
**Scope:** All AFCON360 engineering work.
**Version:** 1.0

---

## 1. The EGGE Loop

Every work item runs:

UNDERSTAND → MAP → TRACE → PROVE → MINIMAL CHANGE → VERIFY → GATE → RECORD → NEXT

text

No step skipped. No step reordered. If a step cannot be completed,
the work item is BLOCKED, not PASS. Partial is BLOCKED.

### 1.1 What is a work item?

A work item is one node: one behavior, one contract, one change, one proof, one gate. Never two. One work item per session, unless the contract says otherwise.

### 1.2 The EGGE steps in detail

1. **UNDERSTAND** — read the work item and the contract. State the guarantee in your own words.
2. **MAP** — locate everything the behavior touches: models, routes, services, templates, tests, config.
3. **TRACE** — read the actual code path for the behavior. Note line numbers.
4. **PROVE** — run the commands that prove current behavior. Record output.
5. **MINIMAL CHANGE** — change the smallest possible surface.
6. **VERIFY** — re-run the proof commands. Confirm the guarantee holds.
7. **GATE** — pass / fail / blocked / deferred. No middle values.
8. **RECORD** — write the evidence file and the record file. Never touch the register.
9. **NEXT** — choose the next work item. Confirm with the human.

---

## 2. The Node Model

Every work item is a node.

| Field | Meaning |
|-------|---------|
| Node ID | A code like `CONTEXT-SWITCH-E2E` or `RESERVATION-CALLBACK-IDEMPOTENCY` |
| Contract | The human's intent, written before any code |
| Evidence | The raw proof, written by the agent after the human confirms PASS |
| Record | The history, written by the agent after the human confirms PASS |
| Gate | PASS / FAIL / BLOCKED / DEFERRED |
| State | OPEN / BLOCKED / DEFERRED / CLOSED |

Closed nodes stay closed. **DO NOT REOPEN.**

---

## 3. The Contract (filled before any code)

Every node produces exactly one contract at `docs/transport/nodes/<node-id>-contract.md`.

The contract has nine sections: Guarantee, Current Behavior, Scope-In, Scope-Out, Interface Contract, Proof of Done, Rollback, Constraints, Acceptance Criteria.

An empty section blocks the node. A vague section blocks the node. A section written by the agent blocks the node. **The contract is written by the human. Full stop.**

---

## 4. The Prompt Sequence (given to the agent)

Four prompts, in order, never combined.

1. **Planning** — agent produces a plan, no code.
2. **Approval** — human corrects or approves, one file at a time.
3. **Step Execution** — agent modifies one file, runs one command, stops.
4. **Proof and Documentation** — agent runs proof, writes evidence + record, does not touch the register.

---

## 5. The Gate Vocabulary

Four values. No others.

- **PASS** — guarantee holds, proof exists, register updated same day.
- **FAIL** — implementation does not satisfy the guarantee.
- **BLOCKED** — cannot proceed due to external or architectural blocker.
- **DEFERRED** — intentionally postponed, with a recorded reason.

Blocked is not Pass. Deferred is not Pass. Partial is not Pass.

---

## 6. The Sage — stale legacy state

A recurring class of defect on this system is **stale legacy state**: a session key, an old column, a legacy digest, a deprecated branch that is still read, a leftover value written by a prior version of the code that shadows the current canonical value. The old state was legitimate once; it is now wrong. It does not get fixed by adding another fallback; it gets fixed at the source.

Sage rule: **when you find stale legacy state, do not paper over it. Trace where the stale value is written, who reads it, and what the canonical source is. Record it as a first-class finding.**

---

## 7. The Case Enumeration Pattern

Behavior must be proven in cases, not in examples. State the cases up front:

- **Case A** — Organisation → Personal.
- **Case B** — Personal → Organisation.
- **Case C** — Organisation → Other valid context (if supported).

For every case: state how the switch is triggered, which keys are written, which rendered surface reacts, and what the proof command is. If a case is not supported, say so explicitly. Do not imply coverage you have not proven.

---

## 8. The URL / ID Safety Rules (non-negotiable)

- URLs use `public_id` (or an approved slug). Never an internal PK.
- API responses use `public_id`. Never internal `id`.
- Session and context keys use canonical names; legacy keys are fallback only and must fail validation.
- Never render `org_id=`, `user_id=`, or any internal id in templates.
- If a route resolves an internal PK and renders it, that is a defect even if the tests pass.

---

## 9. The Default-Action Rule for Unknown Behaviour

When a decision is forced by a gap in evidence:

- If the display/session/context system cannot determine the canonical context, render the **personal** context.
- If a canonical key exists, it wins. If only a legacy key exists, the legacy value must still pass validation — otherwise the personal fallback wins.
- Do not invent a "default organisation". Favour the personal context.
- Do not restore, widen, or adapt legacy keys unless the node explicitly authorizes it.

---

## 10. The Stale-Digest Rule

A "digest" (a snapshot of a value at write time) is legitimate only when the system reads it as a snapshot. When a digest shadows live state, the digest is the bug. Remove the shadow at the source; do not add another snapshot on top of it.

---

## 11. The Canonical-Service Rules (non-negotiable)

If a canonical service already owns a business operation, use it.

| Operation | Canonical Service |
|-----------|-------------------|
| Fare calculation | `fare_service` |
| Availability | `availability_service` |
| Assignment | `assignment_service` |
| Offers | `offer_service` |
| Cross-module writes | `coordination_contract` |
| Identity/context | `app.auth.context` |

A feature that adds a second fare path is not a feature. It is a bug.

---

## 12. The Scope Rules (non-negotiable)

One node per session. Never two.

The roadmap controls scope. Nothing else.

Discovered unrelated issues are recorded in Follow-ups. Not fixed now.

No migrations unless explicitly authorized in the contract. When authorized, migrations MUST be generated by `flask db migrate` from the real model metadata, inspected before `flask db upgrade`, and never hand-edited.

- Agents never run `flask db migrate` or `flask db upgrade`. Modify models, verify metadata, then STOP.
- Agents never edit a generated migration file.
- Tests run against `afcon360_test` only. Never production.
- Agents never modify `tests/conftest.py` or shared fixtures. A failing test is fixed in the node's own test file, or in the code if the code is the cause. Never in scaffolding.

No changes to wallet, base models, or closed workstreams unless explicitly authorized.

---

## 13. The Session Rhythm

Hour 0 — Preparation (human): read the node, write the contract.
Hour 0.5 — Planning (agent): send Prompt 1, review the plan.
Hour 1 — Execution (agent): one file, one diff, one review.
Hour 2 — Proof (human, clean checkout): run every Section 6 command yourself.
Hour 2.5 — Record (agent, human review).
Hour 3 — Close: update register, single commit, do not start another node.

---

## 14. The Failure Recovery Rules

Proof fails twice → revert. Rewrite contract Section 6.

Agent touches Scope-Out → revert. Rewrite contract Section 4.

Migration breaks staging → run rollback SQL. Rewrite contract Sections 5 and 6.

Agent proposes a "while we're here" → say no. Add to Follow-ups.

Diff is larger than expected → revert. Ask for a smaller diff.

Test fails but Scope-In files are clean → the failure is in test scaffolding. Only fix it in the node's own test file, never in shared fixtures.

---

## 15. The Record (written the same day as PASS)

At `docs/transport/nodes/<node-id>-record.md`:

```markdown
# <node-id> — Record

Status:          PASS
Commit:          abc1234
Date:            2026-MM-DD
Owner:           [name]

Files changed:
  - path/to/file.py   (+12 -4)

Evidence:
  See docs/transport/nodes/<node-id>-evidence.md

Runtime verification:
  [curl output | browser screenshot | device test]

Residual risk:
  [specific, honest, one paragraph]

Follow-ups:
  [any discovered issues recorded but NOT fixed]

Gate reference:
  Edition 2.0, Part XIX, row X.Y
```

---

## 16. The Ownership Rules (non-negotiable)

Before editing any code, answer:

Who owns this state?

Which service is the canonical authority?

Which module owns the business rule?

Who is allowed to change it?

Which context is this operating under?

If unclear, the node is BLOCKED.

`current_user ≠ active organisation ≠ membership ≠ capability ≠ authorization`.

---

## 17. The One-Sentence Summary

Evidence before edits. One node at a time. The gate is the proof. The register is the truth.

---

## 18. Who Writes What

Three files per node. Three different authors. No exceptions.

| File | Author | Timing |
|------|--------|--------|
| `<node-id>-contract.md` | HUMAN | Before any code |
| `<node-id>-evidence.md` | AGENT | After the human confirms PASS |
| `<node-id>-record.md` | AGENT | After the human confirms PASS |

The contract is the human's intent. If the agent writes it, the agent also writes the scope, the constraints, and the acceptance criteria — and then grades itself against criteria it chose.

The evidence is the raw proof. The agent may run the proof commands and paste the raw output. It may not summarize. It may not clean. It may not omit a failing test.

The record is the history. The agent fills the template with the commit hash, files changed, residual risk, and follow-ups. The human reviews before it is committed.

The register is updated by the HUMAN, never by the agent.

---

### 18.1 Reconciliation Contract — delegated register transcription

The register is normally written by the human. One exception exists:
when the human has already decided PASS/FAIL/BLOCKED/DEFERRED for a
node, that decision is recorded in the node's -record.md, and the
register has simply not been updated yet, the transcription of that
decision into the register MAY be delegated to an agent under a
Reconciliation Contract.

A Reconciliation Contract is written by the human before any agent
edits a file. It names every register row to be changed with its
target state, names the -record.md that is the source of truth for
each row, requires the agent to produce a diff and STOP without
committing, and forbids any state not named in the contract.

An agent acting under a Reconciliation Contract MAY NOT decide any
state on its own judgment, reopen a closed node, edit any
-contract.md, -evidence.md, or -record.md file, or commit. Human
review of the diff and the commit remain human steps. The contract
may be authored by the human using any tool; the human is the
author, the agent is the scribe.

*End of Operating System, Version 1.0*