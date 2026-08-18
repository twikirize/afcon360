# Kilo Worker Adapter

The repository root `AGENTS.md` is authoritative for Kilo and every other
current or future agent. This file contains only Kilo-specific dashboard
execution context and must not redefine identity, security, database, wallet,
migration, graph, or ownership rules.

Before acting, Kilo must classify the task using the root constitution's
`TRIVIAL`, `LOCAL`, `BEHAVIORAL`, `ARCHITECTURAL`, and `HIGH_RISK` ladder. Use
project memory to route context and load only the applicable rules, skills,
workflows, and dashboard specification. Kilo must inspect before modifying,
stay within the authorized scope, verify proportionally to risk, and return
the root constitution's evidence-based completion report. Internal `id`
values remain private; any UI-visible or URL identifier must use `public_id`.

Memory is not a replacement for current-code verification. Update durable
project memory only when a task changes a reusable decision, invariant,
ownership boundary, hazard, or deferred-work item; routine dashboard edits do
not need memory entries.

## Your Workflow:
1.  Read `DASHBOARD_RESTRUCTURING_PLAN.md` to understand the current phase and tasks.
2.  Implement the tasks for the CURRENT phase.
3.  Update the `DASHBOARD_RESTRUCTURING_PLAN.md` file by checking off completed tasks and adding an entry to the "Implementation Log."
4.  Stop and wait for verification after each phase.

## Current Goal: Phase 1 (Stabilize Shell & CSS Refactor)
- **Target Files:**
    - `templates/user/base_user_dashboard.html`
    - `templates/user/user_dashboard.html`
    - `static/css/modules/user/dashboard.css` (New)
    - `static/css/modules/user/shell.css` (New)
- **Specific Instructions:**
    - Extract all inline styles (`style="..."`) into the new CSS files.
    - Implement the "Dark Editorial" theme (Black/Dark Grey background, Gold/White accents).
    - Remove inline JS handlers (`onclick`, etc.) and replace them with data-attributes (e.g., `data-action="toggle-nav"`).
    - Ensure the "Pane Loading" (`?_pane=1`) still works perfectly.

## Verification Requirements:
- No purple (#667eea) remains in the UI.
- No inline styles in the HTML files.
- The layout remains responsive.
