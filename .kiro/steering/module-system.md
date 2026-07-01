# AFCON360 — Module Toggle System

## Overview
Modules can be enabled/disabled at runtime without code changes.
- Toggle service: `app/services/module_toggle_service.py`
- Guard decorator: `app/utils/module_guard.py`
- Disabled page: `templates/module_disabled.html`
- Module state stored in `SystemConfig` model (`app/models/system_config.py`)
- Hot-reload middleware: `app/middleware/reload_modules.py`

## Gated Modules
events, accommodation, transport, wallet, tourism, tournament

## Usage
- `@module_required('module_name')` gates routes — preserve this on existing routes
- Owner toggles modules via `/owner/module-settings` (`templates/owner/module_settings.html`)
- Module state is app-wide, not per-user

## Rules When Modifying Routes
- Check if the blueprint uses `@module_required` — always preserve it
- New routes inside a gated module must inherit the module guard
- Do not remove module guards without explicit instruction
