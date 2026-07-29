# Plan: Match Accommodation Moderation Styling to Global AFCON360 Theme

**Target page:** `/accommodation/moderate/property/3` (`templates/accommodation/moderate_property.html`)  
**Shared assets:** `moderate_base.css`, `moderate_detail.css`, `moderate.html`, `moderate_review.html`

---

## 1. Root Cause

The accommodation moderation pages (`moderate_property.html`, `moderate.html`, `moderate_review.html`) use a **custom dark theme** defined in `moderate_base.css` with variables like `--ink: #0a0a0f`, `--surface: #0f0f1a`, `--gold: #d4a843`. This does not match the **global AFCON360 theme** loaded by `base.html`, which is light-mode with green/gold brand colors (`--brand-primary: #2d5a2d`, `--brand-accent: #ffcc00`).

Additionally, `moderate_property.html` contains **13 inline `style=` attributes** on layout containers, violating the project rule: *"Inline styles are forbidden on layout containers; extract to CSS classes."*

---

## 2. What "Match the Theme" Means

- **Backgrounds:** Use `--bg-surface` (white) for panels, `--bg-surface-alt` for panel headers
- **Borders:** Use `--border-light` / `--border-medium` instead of `rgba(255,255,255,0.07)`
- **Text:** Use `--text-primary`, `--text-secondary`, `--text-muted` instead of custom `--text` / `--muted`
- **Brand colors:** Use `--brand-primary` (green) and `--brand-accent` (gold) instead of custom `--gold`
- **Semantic colors:** Use `--success`, `--danger`, `--warning` for approve/reject/flag actions
- **Typography:** Use global `--font-family-heading` / `--font-family-body` / `--font-family-mono`
- **Components:** Align `.panel`, `.panel-header`, `.panel-body`, `.btn`, `.badge`, `.form-*`, `.table` with `theme-components.css` overrides
- **Mobile:** Add responsive breakpoints (≤480px phones, ≤1024px tablets) with stacked layouts and horizontal table scroll

---

## 3. Implementation Steps

### Step A — Rewrite `moderate_base.css`
Replace the custom dark-theme variable block and class definitions with global theme variables.

- **Remove:** `@import` of Google Fonts (already in `base.html`)
- **Remove:** custom `--ink`, `--surface`, `--panel`, `--border`, `--gold`, `--gold-dim`, `--text`, `--muted`, `--red`, `--green`, `--amber`
- **Update `.mod-header`:** `background: var(--bg-surface-alt)`, border with `--border-light`
- **Update `.mod-badge`:** `background: var(--brand-primary)`, `color: #fff`
- **Update `.mod-title`:** `color: var(--text-primary)`
- **Update `.btn-ghost`:** Use `--border-light`, hover with `--brand-primary` / `--brand-accent`
- **Update `.btn`:** Use theme spacing (`var(--space-*)`) and font weights
- **Update `.btn-approve`:** `background: var(--success)`, `color: #fff`
- **Update `.btn-reject`:** `background: var(--danger)`, `color: #fff`
- **Update `.btn-flag` / `.btn-warning`:** `background: var(--warning)`, `color: #000`
- **Update `.btn-action`:** Use `--brand-accent` / `--brand-primary-dark`
- **Update `.panel`:** `background: var(--bg-surface)`, `border: 1px solid var(--border-light)`, `border-radius: var(--radius-lg)`
- **Update `.panel-header`:** `background: var(--bg-surface-alt)`, border-bottom with `--border-light`
- **Update `.panel-title`:** `color: var(--text-primary)`, use `--font-family-heading`
- **Update `.panel-icon`:** `background: var(--brand-primary-light)`, `color: var(--brand-primary)`
- **Update `.panel-body`:** `padding: var(--space-5)`
- **Update `.action-bar`:** `background: var(--bg-surface-alt)`, border-top with `--border-light`
- **Update `.badge-*`:** Use theme semantic colors with `rgba()` backgrounds matching `theme-components.css`
- **Update `.form-*`:** Align with `theme-components.css` (`.form-control`, `.form-label`, `.form-select`)
- **Add responsive rules:** `@media (max-width: 1024px)` and `@media (max-width: 480px)` for stacked layouts

### Step B — Expand `moderate_detail.css`
Add reusable CSS classes to eliminate inline styles.

- **`.info-grid`:** Keep `grid-template-columns: repeat(2, 1fr)` but use `gap: var(--space-5)`
- **`.info-span-2`:** `grid-column: 1 / -1` (replaces inline `grid-column: span 2`)
- **`.info-item`:** Use theme spacing and fonts
- **`.info-label`:** Use `--font-family-mono`, `--text-muted`, `--font-size-xs`
- ****.info-value:** Use `--text-primary`, `--font-size-sm`
- **`.photo-grid`:** New class for image thumbnails — `display: flex; gap: var(--space-3); flex-wrap: wrap`
- **`.photo-thumb`:** New class — `width: 120px; height: 90px; object-fit: cover; border-radius: var(--radius-md)`
- **`.form-actions`:** New class — `display: flex; gap: var(--space-3)` (replaces inline flex on button groups)
- **`.hidden`:** New class — `display: none !important` (replaces inline `display: none`)

### Step C — Update `moderate_property.html`
Remove all inline `style=` attributes on layout containers and use CSS classes.

| Line(s) | Current (inline) | Replacement |
|---------|------------------|-------------|
| 12 | `style="display: flex; align-items: center;"` | `class="d-flex align-items-center"` (Bootstrap) or `.mod-header-title-row` |
| 44 | `style="font-family: 'DM Mono', monospace;"` | `class="mono"` |
| 66 | `style="grid-column: span 2;"` | `class="info-span-2"` |
| 68 | `style="display: flex; gap: 10px; flex-wrap: wrap; margin-top: 8px;"` | `class="photo-grid"` |
| 70, 74 | `style="width: 120px; height: 90px; object-fit: cover; border-radius: 6px;"` | `class="photo-thumb"` |
| 86 | `style="grid-column: span 2;"` | `class="info-span-2"` |
| 94 | `style="display: inline;"` | Remove entirely (forms are inline by default when wrapped in `.action-bar` flex) |
| 102 | `style="display: inline;"` | Remove entirely |
| 110, 113 | `onclick="...style.display='block'"` | `onclick="document.getElementById('reject-form').classList.remove('hidden')"` (same for `change-form`) |
| 151 | `style="display: none;"` | `class="hidden"` |
| 162 | `style="display: flex; gap: 12px;"` | `class="form-actions"` |
| 170 | `style="display: none;"` | `class="hidden"` |
| 181 | `style="display: flex; gap: 12px;"` | `class="form-actions"` |

**Note:** Keep `property.id` in form actions as-is. The dual-ID exposure is a separate security concern; changing routes to `public_id` requires route/schema changes outside the styling scope.

### Step D — Update `moderate.html` (queue page)
Remove inline styles for consistency (same CSS file is shared).

- Line 12: `style="display: flex; align-items: center;"` → `class="d-flex align-items-center"`
- Line 66: `style="font-weight: 600; color: var(--text);"` → `class="fw-semibold"` (Bootstrap) or custom class
- Line 67: `style="font-size: 11px; margin-top: 2px;"` → `.mono` class with margin utility

### Step E — Update `moderate_review.html`
Remove inline styles for consistency.

- Line 12: `style="display: flex; align-items: center;"` → `class="d-flex align-items-center"`
- Line 57, 62: `style="grid-column: span 2;"` → `class="info-span-2"`
- Line 71: `style="display: inline;"` → Remove
- Line 76, 79, 113, 122, 124: Inline onclick / display styles → Use `.hidden` class and `classList.remove('hidden')`
- Line 85, 103: `style="display: none;"` → `class="hidden"`
- Line 95, 122: `style="display: flex; gap: 12px;"` → `class="form-actions"`

### Step F — Add Mobile Responsive Rules
In `moderate_base.css` and `moderate_detail.css`, add:

```css
@media (max-width: 1024px) {
  .mod-wrap { padding: 20px; }
  .info-grid { grid-template-columns: 1fr; }
  .info-span-2 { grid-column: 1 / -1; }
  .action-bar { flex-wrap: wrap; }
  .action-bar .btn { flex: 1 1 auto; }
}

@media (max-width: 480px) {
  .mod-header { padding: 16px; flex-direction: column; align-items: flex-start; gap: 12px; }
  .mod-title { font-size: 16px; }
  .panel-header { padding: 14px 16px; }
  .panel-body { padding: 16px; }
  .action-bar { padding: 16px; }
  .photo-thumb { width: 80px; height: 60px; }
  .form-actions { flex-direction: column; }
  .form-actions .btn { width: 100%; justify-content: center; }
}
```

---

## 4. Out of Scope

- **Route URL changes:** `/moderate/property/<int:property_id>` currently uses internal `id`. Switching to `public_id` requires route, query, and link updates across the module — separate from styling.
- **`admin/settings.html`:** Uses `.panel` but defines its own inline `<style>` redefinition. Its specificity is unaffected by external CSS changes.
- **`moderate_booking.html`:** Currently empty (0 bytes), no styling needed.

---

## 5. Verification

1. **Visual check:** Open `http://localhost:5000/accommodation/moderate/property/3` and confirm light theme with green/gold brand colors matches the rest of the AFCON360 dashboard.
2. **Inline style audit:** Grep the updated templates for `style="display:` and `style="grid-column:` — should return zero matches on layout containers.
3. **Action buttons:** Test Approve, Suspend, Reject, Request Changes — confirm forms toggle correctly and submit.
4. **Mobile:** Resize browser to ≤480px and ≤1024px — confirm stacked panels, single-column info grid, horizontal table scroll, and full-width action buttons.
5. **Cross-page consistency:** Check `/accommodation/moderate` (queue) and `/accommodation/moderate/review/<id>` — confirm they inherit the updated theme.

---

## 6. Frontend Documentation

Per AGENTS.md §18, update `static/MOBILE_OPTIMIZATION.md`:
- Add `moderate_property.html`, `moderate.html`, `moderate_review.html` to **File Tree** if not present
- Add entries under **Change Log by File** for each modified template and CSS file
- Update **Verification Checklist** if mobile breakpoints were added
- Add `moderate_base.css` and `moderate_detail.css` to **Future Optimization Isolation Plan**
