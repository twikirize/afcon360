# AFCON360 User Dashboard Redesign Plan

This document tracks the progress of the universal user dashboard redesign. 
The goal is to transform the current generic purple/white SaaS dashboard into a high-end, dark-themed, role-aware "Life Dashboard" for AFCON360.

## 🎨 Design Language
- **Theme:** Dark Editorial
- **Primary Accents:** Gold (#D4AF37), White (#FFFFFF)
- **Background:** Deep Charcoal/Black (#121212 or similar)
- **Components:** Card-based, high contrast, clean spacing.

---

## 🚀 Implementation Phases

### Phase 1: Stabilize Shell & CSS Refactor (COMPLETED)
- **Goal:** Remove inline styles, replace generic purple theme with AFCON360 Dark/Gold.
- **Tasks:**
    - [x] Create `static/css/modules/user/dashboard.css`.
    - [x] Create `static/css/modules/user/shell.css`.
    - [x] Refactor `templates/user/base_user_dashboard.html` to remove inline styles.
    - [x] Refactor `templates/user/user_dashboard.html` to remove inline styles.
    - [x] Replace `onclick`, `onmouseover`, `onmouseout` with data-attributes and delegated listeners.
- **Status:** ✅ Completed

### Phase 2: Redesign Home Dashboard (COMPLETED)
- **Goal:** Transform the landing view into an Action Center.
- **Tasks:**
    - [x] Implement new Hero section with "Identity/KYC" status.
    - [x] Implement "Next Action" priority panel.
    - [x] Implement Wallet card with real status indicators (Create/Activate/Deposit).
- **Status:** ✅ Completed

### Phase 3: Cross-Module Journey Cards (COMPLETED)
- **Goal:** Link Events to Transport and Accommodation.
- **Tasks:**
    - [x] Standardize `_reg_card.html` for reuse.
    - [x] Add "Book Transport" and "Find Stay" links based on event data.
- **Status:** ✅ Completed

### Phase 4: Real Context Switching (COMPLETED)
- **Goal:** Make "Personal vs Org" toggle functional.
- **Tasks:**
    - [x] Create/Verify API endpoint for context switching.
    - [x] Update JS to trigger reload on switch.
    - [x] Update Hero/KYC to reflect organisation context.
- **Status:** ✅ Completed

### Phase 5: Role-Aware Navigation & Tiles (COMPLETED)
- **Goal:** Show Admin/Manager workspaces based on permissions.
- **Tasks:**
    - [x] Add backend logic to pass user roles to dashboard.
    - [x] Render Role Workspace tiles dynamically.
- **Status:** ✅ Completed

### Phase 6: Final Integration & Verification (COMPLETED)
- **Goal:** Polish, testing, and final sign-off.
- **Tasks:**
    - [x] Remove all remaining purple/generic styles.
    - [x] Verify mobile responsiveness.
    - [x] Final CSS variable sweep.
- **Status:** ✅ Completed

---

## 📝 Implementation Log

| Date | Phase | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-06-14 | Plan | Initial creation of the restructuring plan. | Gemini CLI |
| 2026-06-14 | Phase 1 | Extracted all inline styles and JS handlers. Implemented "Dark Editorial" theme with Gold/White accents. Stabilized Shell and Pane Loading logic. | Kilo (Gemini CLI) |
| 2026-06-14 | Phase 2 | Redesigned Home Dashboard into an Action Center. Integrated WalletStatusService for real-time banners and action buttons. Implemented Priority Action cards for KYC and upcoming events. | Kilo (Gemini CLI) |
| 2026-06-14 | Phase 3 | Implemented Cross-Module Journey Cards. Redesigned registration cards to include a "Journey" section with context-aware links to Transport and Accommodation based on event city and IDs. Enriched registration data in backend to support these links. | Kilo (Gemini CLI) |
| 2026-06-14 | Phase 4/5 | Implemented real Context Switching (Personal/Org) and Role-Aware Navigation. The dashboard now changes Wallet, KYC, and Hero context based on the session. Added "Role Workspaces" tiles for Event Managers, Transport Admins, etc. | Kilo (Gemini CLI) |
| 2026-06-14 | Phase 6 | Final polish complete. Purged all legacy purple styles. Verified mobile responsiveness and dark-theme consistency. Dashboard is ready for production review. | Kilo (Gemini CLI) |
