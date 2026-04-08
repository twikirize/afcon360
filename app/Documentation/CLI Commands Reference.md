# AFCON360 Flask CLI Commands

## Owner Management
- `flask assign-owner --list` — Show current owner
- `flask assign-owner --user USERNAME` — Assign owner role
- `flask assign-owner --revoke USERNAME` — Revoke owner role

## Database
- `flask db upgrade` — Apply migrations
- `flask db downgrade` — Rollback migrations
- `flask db revision` — Create migration

## Running
- `flask run` — Dev server on http://localhost:5000
- `flask shell` — Interactive Python shell

## Debugging
- `flask routes` — List all registered routes
- `flask routes --sort method` — Sort by HTTP method
