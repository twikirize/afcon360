PROMPT — HARDENING PASS — BATCH 2 of 5

You are performing a read-only hardening audit of a fix register. Do not edit, move, rename, create, or delete any file except app/events/docs/hardening/batch-2.md at the end. Do not commit. Do not run any command that mutates the working tree or database.

INPUTS
- Source register: app/events/Fix_events.md — frozen. Never edit it.
- Rows to harden: every row under §4 categories A, B, and C. That is:
  - Cat A: A-9 through A-17 (9 rows)
  - Cat B: B-1 through B-11 (11 rows)
  - Cat C: C-1 through C-17 (17 rows)
  Total: 37 rows.

ID COLLISION WARNING
Cat B-1..B-6 share IDs with Track B (already hardened in batch 1). Cat C-1..C-9 share IDs with Track C (already hardened in batch 1). Always prefix the Group in your report — "Cat B / B-1", "Cat C / C-1" — so no reader confuses them with the Track rows.

WHAT "HARDEN" MEANS
For each of the 37 rows, produce the following, in this exact schema, starting each with an H3 header:

### Cat <A|B|C> / <ID> — <one-line title>
- Tree sha:                <output of: git rev-parse HEAD>
- Original Where:          <verbatim copy of the "Where:" line from Fix_events.md>
- Verified Where:          <every file path and line number in the current tree where the item's subject lives; or "unverifiable — reason">
- Original Problem:        <verbatim copy of the "Problem:" line from Fix_events.md>
- Verified Problem:        <"reproduced" | "refined as: ..." | "not found">
- Repro command:           <exact shell command you ran>
- Repro output:            <raw output, one line per hit, no "/" separators, no summarising>
- Verification command:    <verbatim from Fix_events.md, or the exact command you ran; if verification is a judgement call not a shell command, use [REVIEW]>
- Verification output:     <raw output of that command, or "REVIEW — <what a human must verify>">
- State at hardening:      Open | Already satisfied | Partial | Blocked | Unknown
- Corrections:             <"none" for a pure confirmation. Otherwise a list of deltas vs Fix_events.md, each phrased: field → original → corrected. Confirmations of correct register text go in Notes, not here.>
- Confidence:              high | medium | low
- Notes:                   <any nuance a reviewer must know>

RULES FOR CLASSIFICATION (same as batch 1)
- Open — the claimed problem is reproduced today.
- Already satisfied — the fix is already in place; Repro output must show the absence.
- Partial — some claimed problem present, some not. Notes must itemize which parts.
- Blocked — cannot determine state because a dependency is unreachable, uncommitted, or ambiguous. Name the blocker.
- Unknown — Where does not resolve in the current tree.

RULES FOR EVIDENCE (same as batch 1)
- git grep over tracked files (git ls-files) only. Never grep the working directory.
- Repro output: raw lines, one per hit, no concatenation with " / ".
- Verification output: raw lines. If the register's verification is a judgement (e.g. "ADR exists"), use [REVIEW] and state what a human must check.
- Tree sha must match git rev-parse HEAD at the time you ran the commands. If it changes mid-audit, stop and return needs-info.

KNOWN CONTEXT
A prior hardening pass (batch 1) found 15 corrections to Fix_events.md, including four wrong cross-module classifications in §5's signal map. The corrected §5 map is now authoritative. Do not trust any register claim about where a symbol is or is not consumed — resolve it yourself with git grep over tracked files.

OUTPUT
Return two sections only.

1. ## HARDENED ROWS — 37 rows in order Cat A-9..A-17, Cat B-1..B-11, Cat C-1..C-17.

2. ## BATCH WRAP-UP — exactly:

TREE SHA: <git rev-parse HEAD>
BATCH: 2 of 5
ROWS PROCESSED: 37
ROWS OPEN: <count>
ROWS ALREADY SATISFIED: <count>
ROWS PARTIAL: <count>
ROWS BLOCKED: <count>
ROWS UNKNOWN: <count>
CORRECTIONS TOTAL: <count of Corrections entries that are deltas, not confirmations>
FILES READ: <count>
COMMANDS RUN: <one per line, exact>
NEW REGISTER DEFECTS FOUND: <one per line, or "none">
UNKNOWNS: <one per line, or "none">
BLOCKERS: <one per line, or "none">
NEXT: <one sentence>

Do not add sections beyond these two. Every row must have all 15 fields. If any row cannot be completed, set State to Unknown and name the reason.

After returning the two sections, write the full response to app/events/docs/hardening/batch-2.md. Nothing else.

Begin.