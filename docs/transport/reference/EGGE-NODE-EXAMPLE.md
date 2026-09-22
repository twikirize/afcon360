# EGGE — CONTEXT SWITCH END-TO-END PROOF

## Objective: Prove that context switching actually changes the operating context and that the base menu follows it

We have already completed:

* Base-navigation stale legacy fallback removal — **PASS**
* Node B legacy-context audit — **DEFERRED**
* Node C `policy.can()` authorization bridge cleanup — **PASS**

Do **NOT** reopen those completed nodes.

The remaining concern is functional:

> We have not yet proven that a user can actually leave Organisation context and switch to Personal/User context or another valid context, with the base navigation changing accordingly.

This node is therefore an **end-to-end context-switch proof and minimal-fix node**.

---

## 1. UNDERSTAND — Establish the Contract

Before editing anything, read and reconcile:

* `UNIFIED_IDENTITY_CONTEXT_SPEC.md`
* current canonical context implementation
* context-switch route/service
* login/default-context behavior
* `inject_sitewide` / base navigation context processor
* base template/navigation conditions
* existing context-switch tests
* existing auth/context tests

Establish the exact canonical contract for:

```text
current_user
active context
context type
organisation identity
session/request state
available contexts
context switch
```

Important:

```text
current_user != active operating context
```

Switching context must NOT:

* log the user out
* replace `current_user`
* mutate authentication identity
* mutate organisation membership
* grant/revoke roles
* change permissions
* modify wallet state
* modify KYC/KYB
* modify database identity records

It should only change the user's **active operating context**.

---

# 2. MAP — Trace the Real Browser Flow

Trace the complete path:

```text
login
  ↓
current/default active context
  ↓
workspace/base page
  ↓
context selector/menu
  ↓
switch request
  ↓
canonical context-switch service/route
  ↓
session/request persistence
  ↓
redirect
  ↓
new request
  ↓
get_active_context()
  ↓
inject_sitewide()
  ↓
base.html
  ↓
context-appropriate menu
```

Identify the actual implementation for each step.

Do NOT assume that the visible context selector is using the canonical context system.

Specifically locate:

* context selector template
* switch endpoint
* switch POST/GET method
* switch service/helper
* canonical session key(s)
* `get_active_context()`
* context validation
* redirect after switch
* base navigation computation

---

# 3. TRACE — Reproduce the Actual Failure

Use the smallest realistic authenticated test/browser flow.

Start with a user who legitimately has:

```text
Organisation context
Personal context
```

and, if the existing application supports it, another legitimate context such as:

```text
Driver
Accommodation Host
Event
```

Do NOT manufacture permissions or identities merely to make the test pass.

Record the exact state before switching:

```text
current_user
active_context
context_type
organisation identity if applicable
visible base menu
request/session state relevant to context
```

Then perform:

### Case A — Organisation → Personal

Expected:

```text
Organisation context
    ↓ switch
Personal context
```

Verify:

* canonical active context becomes Personal
* organisation context is no longer active
* base menu becomes Personal/User menu
* organisation-only navigation disappears
* `current_user` remains unchanged

### Case B — Personal → Organisation

Expected:

```text
Personal context
    ↓ switch
Organisation context
```

Verify:

* canonical active context becomes Organisation
* correct organisation is selected
* organisation menu returns
* personal-only active state disappears

### Case C — Organisation → another legitimate role/context

If the existing implementation supports another context for the same user:

```text
Organisation
    ↓
Driver / Event / Accommodation Host / other valid context
```

Verify the same invariant.

Do NOT invent a new context type for this test.

---

# 4. PROVE — Test the Important Invariants

The central invariant is:

```text
BASE NAVIGATION MUST FOLLOW CANONICAL ACTIVE CONTEXT,
NOT STALE LEGACY SESSION STATE.
```

Prove these cases:

| Active context     | Expected base navigation        |
| ------------------ | ------------------------------- |
| Personal           | Personal/User navigation        |
| Organisation       | Organisation navigation         |
| Driver             | Driver navigation, if supported |
| Accommodation Host | Host navigation, if supported   |
| Event              | Event navigation, if supported  |

Also prove the reverse transitions.

Especially test:

```text
Organisation
→ Personal
→ Organisation
→ Personal
```

and, where applicable:

```text
Organisation
→ Driver
→ Organisation
```

The menu must change after every switch.

---

# 5. STALE LEGACY STATE TEST

Because Node B established that legacy keys can become stale, explicitly test:

```text
canonical active context = personal
legacy current_context = organization
legacy current_org_id = <old org>
```

Expected:

```text
active context = personal
base navigation = personal
```

Then:

```text
canonical active context = driver/event/host
legacy organization values still present
```

Expected:

```text
base navigation follows canonical context
```

Do not "fix" this by simply deleting all legacy compatibility keys unless the architecture proves they are no longer needed.

---

# 6. URL / ID SAFETY

During every switch and redirect inspect the resulting browser URL.

The public browser URL must not expose:

* internal organisation primary keys
* internal user IDs
* raw database identifiers

If the organisation workspace needs to appear in the URL, use the established public slug/public identifier contract.

Do not introduce a new URL scheme in this node.

---

# 7. MINIMAL CHANGE

If the switch itself is broken:

1. identify the precise ownership defect;
2. make the smallest change necessary;
3. preserve the canonical context architecture;
4. reuse the existing context-switch service/route;
5. do not rebuild context switching;
6. do not modify `policy.can()` — Node C is CLOSED;
7. do not modify the already-fixed `inject_sitewide()` fallback unless new evidence directly proves that fix is wrong.

Do NOT touch:

* migrations
* wallet
* KYC/KYB
* base identity models
* organisation membership model
* unrelated dashboard work
* accommodation logic
* transport logic
* GEO
* provider/consumer architecture

---

# 8. VERIFY — Regression Tests

Add focused regression coverage for the actual defect.

At minimum, prove:

```text
organisation → personal → menu changes
personal → organisation → menu changes
```

If another existing context is available for the same test identity, add:

```text
organisation → other context → menu changes
other context → organisation → menu changes
```

Prefer existing Flask test infrastructure and existing context-switch helpers.

Do not create a parallel fake context architecture.

Run:

### Focused tests

* context-switch tests
* base navigation tests
* auth/context tests
* Node C policy tests

Then run the smallest relevant integration/E2E group.

Report exact commands and counts.

---

# 9. GATE

Only mark:

```text
GATE = PASS
```

if the actual switch flow has been proven end-to-end.

PASS requires evidence that:

```text
Organisation
    ↓
Personal
```

actually works and the base menu changes.

Also prove the reverse:

```text
Personal
    ↓
Organisation
```

If another valid context exists and is already supported, prove that too.

If the switch route/service is still broken, report:

```text
GATE = BLOCKED
```

or

```text
GATE = DEFERRED
```

with the exact blocker.

Do NOT mark PASS merely because unit tests around `get_active_context()` pass.

---

# 10. RECORD

If PASS, record:

* exact root cause
* exact files changed
* exact canonical context state used
* exact switch flow proven
* navigation behavior proven
* regression tests
* test counts
* URL/ID safety result
* any remaining legacy compatibility keys
* next roadmap node

If no code change was required, explicitly say:

```text
NO CODE CHANGE REQUIRED
```

and document the proof.

## Final report format

```text
NODE: CONTEXT-SWITCH-E2E

UNDERSTAND:
...

MAP:
...

TRACE:
...

ROOT CAUSE:
...

CHANGE:
...

PROOF:
Organisation → Personal: PASS/FAIL
Personal → Organisation: PASS/FAIL
Organisation → Other Context: PASS/FAIL/N/A
Other Context → Organisation: PASS/FAIL/N/A

BASE NAVIGATION:
Personal: PASS/FAIL
Organisation: PASS/FAIL
Other Context: PASS/FAIL/N/A

STALE LEGACY STATE:
PASS/FAIL

URL / ID SAFETY:
PASS/FAIL

TESTS:
...

GATE:
PASS / FAIL / BLOCKED / DEFERRED

NEXT:
...
```

### Critical instruction

Do not move to the next Node D/login-default-context work merely because Node C passed.

**First prove that the user can actually leave Organisation context and that the base menu follows the selected canonical context.**