# Fix 2.4 — Evidence

## Command 1 — pytest
pytest tests/transport/test_tile_provider_config.py -v

### Output
```
tests/transport/test_tile_provider_config.py::test_default_config_uses_osm PASSED [ 33%]
tests/transport/test_tile_provider_config.py::test_env_override_changes_url_template PASSED [ 66%]
tests/transport/test_tile_provider_config.py::test_both_templates_render_config_values PASSED [100%]
======================= 3 passed, 4 warnings in 12.73s ========================
```

## Command 2 — default path emits OSM (fresh process)
```
env-clean-url: True
env-clean-attr: True
home status: 200
new-home status: 200
home: True
new-home: True
```

## Command 3 — env override proof, then cleared
```
override status: 200
override-url: True
override-attr: True
osm-url-absent: True
cleared-url: True
cleared-attr: True
```

## Command 4 — targeted git proof
=== geo-map.js ===
(no output = unchanged)

=== five Fix 2.4 files ===
```
 app/config.py                     |  13 +++++
 app/transport/routes.py           | 105 ++++++++++++++++++++++++++++++++------
 templates/transport/home.html     |   4 +-
 templates/transport/new_home.html |   4 +-
 4 files changed, 107 insertions(+), 19 deletions(-)
```

git status --short: ?? tests/transport/test_tile_provider_config.py (new, untracked)

## Template proof table
| Template           | Config URL | Config attribution | Hardcoded OSM removed |
|--------------------|-----------|-------------------|----------------------|
| home.html          | PASS      | PASS              | PASS                 |
| new_home.html      | PASS      | PASS              | PASS                 |

## Environment
Date: 2026-09-23
Branch: main
Python: 3.13.14
OS: Windows

## Result
All commands passed. Fix 2.4 gate: PASS.