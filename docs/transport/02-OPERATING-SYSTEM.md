
---

## How to Use It

**Do this today:**

1. Create `docs/transport/fixes/00-OPERATING-SYSTEM.md` and paste the file above.
2. Create the empty `Fix-1.1-contract.md` and `Fix-1.1-record.md` next to it.
3. Copy the Fix 1.1 contract from the playbook (Section 9 of the playbook) into the empty file. Adjust file paths to match your current tree.
4. Open opencode. Send Prompt 1.

**Do NOT do this:**

- Do NOT merge the manifesto, the playbook, and EGGE into one giant document. That is how you get an unreadable 40,000-word file that nobody opens.
- Do NOT create additional process files. Three documents — Manifesto, Playbook, Operating System — is the correct count. Adding a fourth is bureaucracy.
- Do NOT let the agent "helpfully" rewrite the operating system. It is the fixed point.

---

## What EGGE Actually Is

Your EGGE document is not a new thing. It is the same loop the playbook already describes, phrased as a discipline rather than a set of steps. The two documents were describing the same shape from different angles.

The correct move is not to keep both. It is to **keep the loop** and delete the duplication.

So:

- **Delete** the standalone `AFCON360 EGGE IMPLEMENTATION STRATEGY.txt` after the operating system file is created. Its content is now the operating system's Chapter 1.
- **Keep** `Edition 2.0 Manifesto` as the charter. Never touch it during a fix.
- **Keep** `Implementation Playbook` as the reference for template details and evidence matrix. Open it only when writing a contract.
- **Open** `00-OPERATING-SYSTEM.md` every single session.

That is the entire answer.

---

**Ready when you are.** Write the Fix 1.1 contract next and I'll review it before you hand it to the agent. That is the next real step, and it is the same step it has been for the last several messages. The book, the playbook, the operating system — all three are now complete enough to run the first fix.

Run it.

---

## Agent-Behaviour Rule (learned during Fix 1.1)

When a fix test fails and the failure is NOT caused by a Scope-In file,
do NOT edit shared scaffolding (`tests/conftest.py`, fixtures, DB state)
to make it pass. The cause is almost always test-state leakage that must
be handled inside the fix's own test file.

Concrete Fix-1.1 example: `_isolate_db` deliberately skips auto-cleanup
for `@pytest.mark.threaded` tests (conftest.py:584). The established
convention is that threaded tests self-clean every row they create
(`tests/test_transport_concurrent_claim.py _delete`). A threaded test
using a FIXED `idempotency_key` leaked its Booking row between runs; the
global unique index `ix_booking_idem` then collided with the next run's
fresh `test_user`, producing an `IntegrityError` in the service and what
looks like a service failure. The fix was in the test file only: unique
per-run keys + `_cleanup_key` in a `finally` block.