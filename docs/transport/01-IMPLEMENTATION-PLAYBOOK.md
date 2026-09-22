# AFCON360 Transport — Implementation Playbook

**Operational companion to Edition 2.0 Manifesto**
**Purpose:** The practical guide for executing every Fix, one at a time, with an AI agent and a human reviewer, until the gate register is green.
**Audience:** The implementing engineer (you) and the operating agent.
**Rule:** Edition 2.0 says *what* and *why*. This playbook says *how*, *in what order*, and *with what evidence*.

---

## 0. Relationship to Edition 2.0

Edition 2.0 is the manifesto — architecture, principles, the fix register, the gate vocabulary.

This playbook is the **execution layer**. It does not repeat the principles. It does not repeat the fixes. It defines:

- The three artifacts every fix produces.
- The templates for those artifacts.
- The prompt sequence you give the agent.
- The evidence required to mark a fix PASS.
- The exact rhythm of a working session.

If Edition 2.0 is the map, this is the driving directions.

---

## 1. The Three Artifacts

Every fix, no matter its size, produces exactly three things. If any is missing, the fix is not complete — regardless of whether the code works.

| # | Artifact | Written by | When | Stored at |
|---|---|---|---|---|
| 1 | **Fix Contract** | Human | Before any code | `docs/transport/fixes/Fix-X.Y-contract.md` |
| 2 | **Evidence** | Agent | After human confirms PASS | `docs/transport/fixes/Fix-X.Y-evidence.md` |
| 3 | **Record** | Agent | After human confirms PASS | `docs/transport/fixes/Fix-X.Y-record.md` |

The **contract is the human's job. Always.** The agent never writes the contract. That is where the discipline lives.

The **evidence and record are the agent's job.** Mechanical work: capture raw output, fill the template.

---

## 2. The Operating Principles

Twelve rules. Memorize the first four; the rest are expansions.

1. **One fix per session.** Never two. Never "while we're here".
2. **The contract is written before the agent sees the code.**
3. **The agent proposes a plan; you approve it before execution.**
4. **You run the proof command. Not the agent.** The agent's summary is not evidence.
5. Every file the agent touches is named in the contract.
6. Every file the agent must not touch is named in the contract.
7. The agent executes one file at a time. You review each diff.
8. No new dependency enters `requirements.txt` without explicit approval.
9. No migration is written without a rollback in the same contract.
10. No test assertion is written by the agent. You write the expectations; the agent writes the code.
11. If the agent asks a question, answer it. If it asks none, verify its assumptions.
12. A fix is done when the gate is PASS and the register is updated. Not before.

---

## 3. The Fix Contract Template

Copy this into `docs/transport/fixes/Fix-X.Y-contract.md`. Fill every section. Empty sections block the fix.

```markdown
# Fix Contract — [Fix ID] — [Name]

## 1. Guarantee
One sentence. What the system guarantees after this fix that it does
not guarantee today. Present tense, future truth.

## 2. Current Behavior
What happens today, verified by reading the code. Quote file + function.

## 3. Scope — Files In
Exact paths. No wildcards. Every file the agent may touch.

## 4. Scope — Files Out
Exact paths. Files the agent must NOT touch even if it thinks it should.

## 5. Interface Contract
Column names, method signatures, HTTP status codes, error kinds, form
field names. The precise shape.

## 6. Proof of Done
The exact command(s) that prove the guarantee holds. Expected output.

## 7. Rollback
Exact steps to reverse the fix if it breaks production.

## 8. Constraints (Do NOT)
Non-negotiable constraints on the implementation.

## 9. Acceptance Criteria
Checkbox list the gate will verify.
4. The Prompt Sequence for the Agent
Four prompts, in order. Never skip. Never combine.

Prompt 1 — Planning
text
Read the Fix Contract below. Do NOT write any code yet.
Produce a plan with:
1. Files to modify, one line each, and why.
2. Smallest set of changes satisfying the Guarantee.
3. Assumptions about existing code, each cited by line number.
4. Questions you need answered.
5. Any Scope-Out file you feel tempted to touch, and why.
Stop after the plan. Wait for approval.
--- CONTRACT ---
[full contract]
--- END CONTRACT ---
Prompt 2 — Approval
Either correct the plan, or:

text
Approved. Execute Step 1 only: modify [exact file]. Then stop and
show me `git diff [file]`. Do not touch any other file.
Prompt 3 — Step Execution
text
Step [N] approved. Modify [exact file] only. Run [exact command]
after the edit and paste the raw output. Then stop.
Prompt 4 — Proof and Documentation
text
All steps complete. Do NOT modify anything further.
Run the proof commands from Section 6. Paste raw output. Do not
summarize.

Then write:
  docs/transport/fixes/Fix-X.Y-evidence.md  — raw command output only
  docs/transport/fixes/Fix-X.Y-record.md    — fill the record template

Do NOT update the manifesto register. That is the human's step.
5. The Gate Vocabulary
Four values. No others.

PASS — guarantee holds, proof exists, register updated same day.

FAIL — implementation does not satisfy the guarantee.

BLOCKED — cannot proceed due to external or architectural blocker.

DEFERRED — intentionally postponed, with a recorded reason.

Rules: Blocked is not Pass. Deferred is not Pass. Partial is not Pass. "It looked fine in the browser" is not Pass.

6. Evidence Matrix
For each fix, the gate requires specific evidence. Not "tests pass" — specific artifacts.

Fix	Required Evidence
1.1	pytest output, git diff --stat showing only Scope-In files, rollback SQL run in staging, curl showing idempotent replay returns same reference
1.2	curl showing SSE stream emits ≥10 events over 60s; reconnect test; browser screenshot of live map
1.3	FCM/APNs delivery receipt; device screenshot of notification; test showing offer TTL and push both occur within 5s
1.4	EXPLAIN ANALYZE showing index scan; matching latency p95 before vs after
1.5	\d+ location_observations showing partition scheme; drop-old-partition test
2.x	Test per fix; EXPLAIN ANALYZE for query optimizations; screenshot for provider migrations
3.x	Lighthouse report for PWA; device screenshot for RN; Playwright screenshot for CSS fixes
If the matrix says "screenshot", a screenshot is required. Not a summary.

7. The Rhythm of a Single Fix
Hour 0 — Preparation (human)
Read the fix in Edition 2.0. Read the current code. Write the contract by hand. All nine sections.

Hour 0.5 — Planning (agent)
Send Prompt 1. Read the plan. Veto anything outside scope.

Hour 1 — Execution (agent)
Prompt 3 for each step. One file. One diff. One review.

Hour 2 — Proof (human, clean checkout)
Run every Section 6 command yourself. If it fails, return to the agent with raw failure output.

Hour 2.5 — Record (agent, then human review)
Agent writes evidence + record. Human reviews.

Hour 3 — Close
Update the register. Single commit. Do not start another fix.

8. Failure Recovery Rules
Proof fails twice → revert the branch. Rewrite the contract's Section 6. The problem is the proof, not the code.

Agent touches Scope-Out → revert. Rewrite the contract's Section 4. Re-run Prompt 1.

Migration breaks staging → run rollback SQL from Section 7. Verify it works. Rewrite Sections 5 and 6.

Agent proposes a "while we're here" → say no. Add it to Follow-ups. Move on.

Diff is larger than expected → revert. Ask for a smaller diff. An 8-line change that became 80 is a refactor.

Test fails but Scope-In files are clean → the failure is in test scaffolding. Only fix it in the fix's own test file, never in shared fixtures.

9. The Fix 1.1 Contract (Reference Example)
The fully-worked Fix 1.1 contract is at
docs/transport/fixes/Fix-1.1-contract.md. It is the reference
example for every future contract. Read it before writing your own.

10. What This Playbook Is Not
Not a manifesto. That's Edition 2.0.

Not the EGGE loop. That's the operating system.

Not a process file. Those exist. Adding a fourth is bureaucracy.

Three documents. Manifesto, Playbook, Operating System. No more.

End of Implementation Playbook, Version 1.0.