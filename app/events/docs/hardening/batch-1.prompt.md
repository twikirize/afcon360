PROMPT — HARDENING PASS — BATCH 1 of 5

You are performing a read-only hardening audit of a fix register. Do not edit, move, rename, create, or delete any file. Do not commit. Do not run any command that mutates the working tree or database. If you find yourself about to write anything except your final response, stop and return needs-info.

Inputs

Source register: app/events/Fix_events.md — this is the draft. It is frozen; never edit it.

Rows to harden in this batch: every row under §1 Priority Track A, §2 Priority Track B, and §3 Priority Track C in that file. That is 23 rows: A-1..A-8, B-1..B-6, C-1..C-9.

What "harden" means

For each of the 23 rows, produce the following, in this exact schema:

text
### [Group] / [ID] — [one-line title]
- Tree sha:                <output of: git rev-parse HEAD>
- Original Where:          <verbatim copy of the "Where:" line from Fix_events.md, including its section markers>
- Verified Where:          <every file path and line number in the current tree where the item's subject actually lives; if the source's Where reference does not resolve, write "unverifiable — <reason>">
- Original Problem:        <verbatim copy of the "Problem:" line from Fix_events.md>
- Verified Problem:        <"reproduced" if the claimed problem is present today, "refined as: <new wording>" if partially true, or "not found" if the claimed problem does not exist in the current tree>
- Repro command:           <the exact shell command you ran to establish Verified Problem>
- Repro output:            <raw output, trimmed to the lines that matter>
- Verification command:    <verbatim copy of the "Verification:" line from Fix_events.md, unless the source text is not a command, in which case write the exact command you will use to prove the fix>
- Verification output:     <raw output of that command against the current tree>
- State at hardening:      Open | Already satisfied | Partial | Blocked | Unknown
- Corrections:             <"none" or a list of deltas vs Fix_events.md, each one phrased as: field → original → corrected>
- Confidence:              high | medium | low
- Notes:                   <any nuance a reviewer must know: e.g. uncommitted files, schema drift, ambiguous source wording>
Rules for classification

Open — the claimed problem is reproduced by your Repro command today.

Already satisfied — the claimed problem is absent today; the fix is already in place. Your Repro output must show the absence.

Partial — some of the claimed problem is present, some is not. Your Notes must itemize which parts are present.

Blocked — you cannot determine the state because a required file or dependency is unreachable, uncommitted, or ambiguous. Name the blocker.

Unknown — the source's Where reference does not resolve in the current tree, and you cannot determine where the item now lives.

Rules for evidence

Every Repro command and Verification command must be a shell command that could be pasted into a fresh terminal and re-run. Use git grep over tracked files (git ls-files) — never grep the working directory, never rely on uncommitted files.

Every Repro output and Verification output must be the raw output of the command you actually ran, trimmed only by removing lines that are not relevant to the item. Do not summarise. Do not paraphrase.

Every row's Tree sha must match the output of git rev-parse HEAD at the time you ran the commands. If the tree sha changes mid-audit, stop and return needs-info.

Known context (verify, do not assume)

A prior audit of this register found four rows in its §5 signal map with incorrect cross-module classifications. Because of that, do not trust any source claim about where a symbol is or is not consumed — resolve it yourself with git grep over tracked files. In particular, for the five signals declared in app/events/signal_handlers.py, find every .send() and .connect() call site in the repository, not only those in app/events/.

Output

Return two sections:

## HARDENED ROWS — the 23 rows in the schema above, in order A-1..A-8, B-1..B-6, C-1..C-9.

## BATCH WRAP-UP — exactly this block, filled in:

text
TREE SHA: <git rev-parse HEAD>
BATCH: 1 of 5
ROWS PROCESSED: <count>
ROWS OPEN: <count>
ROWS ALREADY SATISFIED: <count>
ROWS PARTIAL: <count>
ROWS BLOCKED: <count>
ROWS UNKNOWN: <count>
CORRECTIONS TOTAL: <count of Corrections entries across all rows>
FILES READ: <count>
COMMANDS RUN: <one per line, exact>
NEW REGISTER DEFECTS FOUND: <one per line, or "none">
UNKNOWNS: <anything you could not determine>
BLOCKERS: <anything preventing completion>
NEXT: <one sentence>
If any row is incomplete, set NEXT to name the row and the missing field. Do not pad. Do not invent. Do not add sections beyond the two named.

Begin.