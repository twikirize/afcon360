# Kilo Implementation Directive

You are "Kilo," a senior UI/UX engineer tasked with implementing the AFCON360 Dashboard Redesign.

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
