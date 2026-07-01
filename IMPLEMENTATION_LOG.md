# AFCON360 Universal Agent Activity & Implementation Log

> **MANDATORY INSTRUCTION FOR ALL AGENTS**: This file is the absolute source of truth for all codebase modifications, architectural shifts, and feature implementations. Every agent MUST:
> 1. **Read this log** before starting any task to understand current system state.
> 2. **Update this log** immediately after completing a task with a concise summary of changes.
> 3. **Maintain the "Directives" section** if new project-wide rules are established.

---

## 🚀 Unified Module Toggle System (Completed: 13 June 2026)
**Owner**: Gemini CLI Agent
**Status**: STABLE

### 💎 Summary of Work
Transitioned the platform from inconsistent config-based toggles to a DB-backed, owner-controlled feature flag system.

**Key Changes**:
- **Source of Truth**: PostgreSQL via `SystemConfig` model (`MODULE_FLAGS` key).
- **Lookup Path**: `module_enabled('name')` helper in `app.utils.module_guard`.
- **Consistency**: `reload_modules` middleware refreshes `app.config` from DB per-request.
- **Security**: Toggling restricted to **Owner** and **Super Admin** roles.
- **UI**: Standardized all templates to use `{% if module_enabled('name') %}`.

### ⚠️ Reverted Experiment (Over-Hardening)
Attempted to introduce thread-safe TTL locking and 503 status codes. This was **REVERTED** due to excessive complexity and template rendering breakages. Future agents should prefer the current simplified middleware-sync approach unless performance dictates otherwise.

---

## 📝 Universal Directives for Future Agents
*These rules apply to all work done in this repository.*

1. **Module Gating**: Always use the `module_enabled()` helper from `app.utils.module_guard`. Never read raw config flags.
2. **Database Integrity**: When modifying `SystemConfig`, ensure changes are reflected in the corresponding service layer.
3. **Template Reliability**: Avoid complex dictionary `.get()` logic in Jinja2 templates; use established Python helpers to ensure UI stability.
4. **Documentation**: Every major workstream MUST have an entry in this file.

---

## 🛠️ Upcoming Workstreams / Roadmap
*Add new planned items here.*

1. [Planned] Audit and consolidate all remaining module-specific decorators into `app.utils.module_guard`.
2. [Planned] Standardize all error pages (403, 404, 500) to match the new `module_disabled` aesthetic.

---
*Log initialized by Gemini CLI Agent on Saturday, 13 June 2026.*
