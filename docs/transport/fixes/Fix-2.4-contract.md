# Fix Contract — Fix 2.4 — Tile Provider Migration

**Owner:** [your name]
**Date:** 2026-09-22
**Status:** READY FOR AGENT
**Roadmap reference:** Edition 2.0, Part VII, Fix 2.4
**Report format:** Compact

---

## 1. Guarantee

The tile URL and attribution used by the rider map are supplied by
application configuration (env-driven), not hardcoded in templates.
The default configuration preserves current dev behavior (OSM). In
production, an operator sets `TILE_PROVIDER_URL_TEMPLATE` and
`TILE_PROVIDER_ATTRIBUTION` to a provider permitted for commercial
traffic, with no code change required.

## 2. Current Behavior

Both `templates/transport/home.html` and
`templates/transport/new_home.html` hardcode, inside the inline
`initMap()` IIFE:

    tileUrl: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '\u00a9 OpenStreetMap',

There is no config override. `app/transport/routes.py::home()` and
`new_home()` do not inject tile context. `static/js/geo/geo-map.js`
accepts `tileUrl`/`attribution` as init options, so the plumbing at
the client layer already exists — only the server side is missing a
config passthrough.

Verified by reading:
- `templates/transport/home.html` — hardcoded OSM strings
- `templates/transport/new_home.html` — hardcoded OSM strings
- `app/transport/routes.py` — `home()` and `new_home()` build `ctx`
  without tile keys
- `static/js/geo/geo-map.js` — accepts `tileUrl` and `attribution`
  as init options (no hardcoded default URL)

## 3. Scope — Files In

- `app/config.py`
  → add `TILE_PROVIDER_URL_TEMPLATE` and `TILE_PROVIDER_ATTRIBUTION`
    keys, env override, safe dev defaults (OSM values).

- `app/transport/routes.py`
  → `home()` and `new_home()`: add `tile_url` and `tile_attribution`
    to `ctx`, sourced from `current_app.config`.

- `templates/transport/home.html`
  → replace the two hardcoded strings with `{{ tile_url }}` and
    `{{ tile_attribution|safe }}`.

- `templates/transport/new_home.html`
  → same replacement.

- `tests/transport/test_tile_provider_config.py`
  → new file. Three tests named in Section 6.

## 4. Scope — Files Out

- `static/js/geo/geo-map.js` — accepts URL as a parameter already.
  Do NOT modify unless reading it reveals a hardcoded OSM fallback
  that overrides the passed value. If that is found, STOP and report.
- `app/transport/services/*` (all services)
- `app/transport/api/*` (all API resources)
- `app/transport/models.py`
- `migrations/**` (this node has no migration)
- `requirements.txt`
- `tests/conftest.py`
- Any file under `app/wallet/`, `app/identity/`, `app/auth/`,
  `app/events/`, `app/accommodation/`
- Any template under `templates/transport/bookings/` or
  `templates/transport/admin/`

## 5. Interface Contract

### Config keys (in `config.py`, base `Config` class)

    TILE_PROVIDER_URL_TEMPLATE = os.environ.get(
        "TILE_PROVIDER_URL_TEMPLATE",
        "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
    )
    TILE_PROVIDER_ATTRIBUTION = os.environ.get(
        "TILE_PROVIDER_ATTRIBUTION",
        "\u00a9 OpenStreetMap"
    )

Both keys must be readable from `current_app.config` in any
environment (dev, test, prod).

### Context injection

`home()` and `new_home()` add to the existing `ctx` dict:

    tile_url=current_app.config["TILE_PROVIDER_URL_TEMPLATE"],
    tile_attribution=current_app.config["TILE_PROVIDER_ATTRIBUTION"],

No other keys added.

### Template usage

In both templates, inside `initMap()`:

    var handle = window.GeoMap.init('pickMap', {
      tileUrl: '{{ tile_url }}',
      attribution: "{{ tile_attribution|safe }}",
      center: {latitude: 0.3136, longitude: 32.5811},
      zoom: 12
    });

|safe is required for attribution because providers such as
MapTiler and Mapbox return HTML `<a>` links. The value comes from
server config, not user input.

### Backward compatibility

Default config values are the current OSM strings. A dev environment
that sets nothing sees functionally identical output. A production
operator sets the two env vars to switch providers.

## 6. Proof of Done

### Command 1

    pytest tests/transport/test_tile_provider_config.py -v

Expected: 3 tests pass.
- `test_default_config_uses_osm`
- `test_env_override_changes_url_template`
- `test_both_templates_render_config_values`

### Test mechanics

- `test_env_override_changes_url_template`: manipulate the env var via
  `os.environ`, then re-read the config with `importlib.reload` on
  `app.config`, asserting the new template value is picked up. The
  module is reloaded so the `os.environ.get(...)` default is re-read.
- `test_both_templates_render_config_values`: set the values directly
  on the session app with `app.config.update(...)` (no env / reload),
  request both `/transport/` and `/transport/new-home`, and assert the
  configured URL/attribution appear in the rendered HTML.

### Command 2

The original `python -c "...\<newline>..."` form is bash syntax.
PowerShell treats backslash as a literal, so the contract uses the
same temp-script pattern proven in the manual Step 2/3 proofs:

    - write a small temp script to %TEMP%\opencode\fix24_proof2.py
    - sys.path.insert(0, repo_root)
    - run it with .venv\Scripts\python.exe
    - delete the temp script afterward

Proof semantics (unchanged): fresh Python process, no env override,
request both `/transport/` and `/transport/new-home`, assert
`tile.openstreetmap.org` appears in both bodies — the OSM default
path still works. If `/transport/` requires auth (302) on an install,
the agent reports that and uses `/transport/new-home` only; the
default-path proof is still valid on the route that returns 200.

Expected:
    home: True
    new-home: True

### Command 3 (env override proof)

Set the env vars in the parent shell first, then run a temp script
(same pattern as Command 2) that requests `/transport/new-home` and
asserts the override URL/attribution appear AND the OSM URL does not.
Then unset the env vars in the parent shell.

    $env:TILE_PROVIDER_URL_TEMPLATE = "https://tiles.example.test/{z}/{x}/{y}.png"
    $env:TILE_PROVIDER_ATTRIBUTION = "<a href='https://example.test'>© Example</a>"
    # run %TEMP%\opencode\fix24_proof3.py with .venv\Scripts\python.exe

Expected:
    override-url: True
    override-attr: True

Then clear the env vars:
    Remove-Item Env:TILE_PROVIDER_URL_TEMPLATE
    Remove-Item Env:TILE_PROVIDER_ATTRIBUTION

### Command 4

`git diff --stat main` is replaced by a targeted check. `main` is
behind several sessions of uncommitted work (T-10, My Trips, all of
Fix 2.4), so a comparison against it would conflate Fix 2.4 with
unrelated work and make the expected result impossible to interpret.

    1. git diff --stat -- static/js/geo/geo-map.js
       Expected: no output (file unchanged).

    2. git diff --stat -- app/config.py \
                          app/transport/routes.py \
                          templates/transport/home.html \
                          templates/transport/new_home.html \
                          tests/transport/test_tile_provider_config.py
       Expected: only these five Fix 2.4 files appear. Every other
       file in the working tree (T-10, My Trips, etc.) is out of
       scope for Fix 2.4 and is not part of this proof; unrelated
       working-tree changes are preserved and disclosed, not hidden.

## 7. Rollback

    git revert <commit-sha-of-this-node>

No migration. No data. No state. Estimated rollback time: under 30
seconds.

## 8. Constraints (Do NOT)

- Do NOT modify `static/js/geo/geo-map.js`. It accepts `tileUrl` and
  `attribution` as init parameters. If it hardcodes a URL that
  overrides the parameter, STOP and report — do not edit.
- Do NOT add a dependency.
- Do NOT introduce a new config framework. Use the existing
  `config.py` class hierarchy.
- Do NOT add keys to any other `Config` subclass (dev/test/prod)
  unless required to override the base — env var is the override
  mechanism.
- Do NOT change any other transport template.
- Do NOT modify any migration.
- Do NOT modify `tests/conftest.py`.
- Do NOT commit. Propose and stop.
- Do NOT run `flask db migrate` or `flask db upgrade` (this node has
  no migration).

## 9. Acceptance Criteria

- [ ] `TILE_PROVIDER_URL_TEMPLATE` and `TILE_PROVIDER_ATTRIBUTION`
      exist in `config.py` with env overrides.
- [ ] `home()` and `new_home()` inject `tile_url` and
      `tile_attribution` into context.
- [ ] Both templates use `{{ tile_url }}` and
      `{{ tile_attribution|safe }}`, no hardcoded OSM string remains.
- [ ] 3 tests pass.
- [ ] Default dev output still contains `tile.openstreetmap.org`.
- [ ] Env override proof passes (Command 3).
- [ ] `git diff --stat main` shows only Section 3 files.
- [ ] No new dependency.
- [ ] No migration in the diff.

## Notes for the Agent

Read `config.py`, `app/transport/routes.py::home()` and `::new_home()`,
both rider templates, and `static/js/geo/geo-map.js` before
proposing a plan. The point of this node is to make tile source
configurable, not to switch providers — the operator selects the
provider via env vars.

Do not write code until the human approves your plan.