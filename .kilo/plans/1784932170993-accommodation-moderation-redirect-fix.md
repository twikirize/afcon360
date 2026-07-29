# Fix Accommodation Admin Page Links & Deprecate Duplicate Pending Properties Page

## Problem
- `app/accommodation/routes.py` moderation routes already redirect to `admin_properties` (comprehensive dashboard).
- Two templates still reference the old `accommodation.pending_properties` endpoint:
  1. `templates/accommodation/admin/pending_properties.html` — pagination links
  2. `templates/accommodation/admin/property_history.html` — back button
- This creates a stale "Pending Properties" page that is narrower than the main dashboard and causes confusion after moderation actions.

## Decision
Remove the duplicate page by redirecting its route to the unified dashboard, and update all template links accordingly.

## Implementation Tasks

### 1. Update template links
**Files:**
- `templates/accommodation/admin/pending_properties.html`
- `templates/accommodation/admin/property_history.html`

**Changes:**
- Replace all `url_for('accommodation.pending_properties', ...)` with `url_for('accommodation.admin_properties', ...)`
- In `property_history.html`, change button text from `Back to Pending Properties` to `Back to Properties`

### 2. Deprecate the route
**File:** `app/accommodation/routes.py`

**Change:**
- Replace the `pending_properties()` view function with a redirect:
  ```python
  @accommodation_bp.route('/admin/pending-properties')
  @login_required
  @require_role('admin', 'moderator', 'owner')
  def pending_properties():
      return redirect(url_for('accommodation.admin_properties', workflow_stage='under_review'))
  ```
  This preserves the URL for any external bookmarks while landing on the unified dashboard pre-filtered to the closest attention-queue equivalent.

### 3. Update MOBILE_OPTIMIZATION.md
If `pending_properties.html` is no longer rendered as a full standalone page, update:
- File tree section if the template is removed
- Change log to note link redirects
- If template remains but is only a redirect target, note it as deprecated

## Verification
1. Visit `/admin/pending-properties` — should redirect to `/admin/properties?workflow_stage=under_review`
2. Pagination in the old page area resolves to `/admin/properties?page=N`
3. Property history back button goes to `/admin/properties`
4. Moderation actions (approve, reject, suspend, reinstate) continue to land on `/admin/properties`
5. No template or route references to `accommodation.pending_properties` remain besides the redirect itself

## Migration
No database migration required.

## Risks / Conflicts
- Low risk: only route/template changes, no schema or business-logic changes.
- The old page is still accessible via URL but immediately redirects; no 404 break for bookmarked links.
- `pending_properties.html` can remain in templates as a fallback, but it should not be actively rendered. If desired, the implementation agent may remove it after confirming no other references exist.

## Open Questions
None — implementation-ready.
