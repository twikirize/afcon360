# AFCON360 Fresh-Database Replay Investigation Log

**Status:** Active investigation — not a replay sign-off  
**Scope:** Disposable Docker/Codespaces replay using the H3-A root migration and the normal active Alembic chain  
**Branch:** `sandbox/codespaces-alembic-investigation`  
**Main branch:** Do not merge this investigation work until the replay gates are passed and reviewed.

This is an evidence log, not a list of assumed causes. Append new findings as they are reproduced. Keep four concepts separate: **observed evidence**, **confirmed cause**, **temporary workaround**, and **durable correction**.

## Replay target and acceptance gates

Expected active chain:

```text
h3a20261020
  -> c076b257b11d
  -> 1792869659
  -> d3ba8c51f407
  -> 1793011323
  -> 1793013676
```

The replay is **not PASS** until an empty disposable PostgreSQL database starts from H3-A, every normal migration completes in order, the Alembic version is verified as `1793013676`, and the application health endpoint responds successfully. Also record table/schema checks and any required post-replay integrity checks separately. Image build or service health alone is not migration success.

## Evidence ledger

### RPL-01 — Host Python is not the project runtime

- **Observed:** A dependency install executed with Codespaces host Python 3.14.2 failed while building pinned `pydantic_core==2.27.0`. PyO3 0.22.5 explicitly reported that Python 3.14 exceeded its supported maximum of 3.13.
- **Resolution used:** Run dependency installation through the repository's Dockerfile, which starts from `python:3.13-slim`; do not change dependency pins just to hide the runtime mismatch.
- **Verification:** Docker application image built successfully at source commit `69d6b7974b4792bade62489fa0d8dfa7eee0f077`.
- **Durable correction to consider:** Document the supported Python runtime and make local/replay instructions use the Docker image or a matching Python 3.13 environment. Avoid unqualified `pip install -r requirements.txt` under whatever Python Codespaces happens to provide.
- **Status:** Environment workaround verified; wider developer onboarding/documentation review pending.

### RPL-02 — PostgreSQL server-version-specific baseline setting

- **Observed earlier:** The baseline SQL contains `SET transaction_timeout = 0;`; the replay on PostgreSQL 15 failed with `unrecognized configuration parameter "transaction_timeout"`.
- **Branch change:** The active H3-A migration now detects `server_version_num` and removes only this one statement for server versions below PostgreSQL 17. PostgreSQL 17+ retains the original SQL; the helper fails closed if the expected statement is missing or duplicated. Regression tests were added in `tests/test_h3_baseline_pg_version_compat.py`.
- **Verification:** The targeted tests passed: **9 passed**.
- **Invariant:** Do not rewrite the approved baseline schema SQL or its provenance hash as part of this compatibility handling.
- **Status:** Targeted helper tests PASS; actual migration execution on the target PostgreSQL version is still **unverified**.

### RPL-03 — PostgreSQL 18 data-volume mount layout

- **Observed earlier:** The PostgreSQL 18 image refused to start against the legacy `/var/lib/postgresql/data` mount layout, reporting that the data appeared in an unused mount.
- **Branch change:** Compose now uses `postgres:18-alpine`, mounts the new named volume `postgres_data_pg18` at `/var/lib/postgresql`, and leaves the old volume name untouched. The web port mapping is `5000:5000`.
- **Verification:** A clean PostgreSQL 18.6 cluster initialized and reported healthy.
- **Safety:** Do not delete the old volume or use `docker compose down -v`. Confirm the actual volume name and database identity before any future replay or cleanup.
- **Status:** Startup/layout issue resolved in the disposable environment; data-preservation and full-replay gates remain open.

### RPL-04 — Compose-network TCP connectivity fails despite healthy services

- **Observed:** PostgreSQL and Redis both report healthy. A temporary container attached to the Compose network resolves `db` to `172.18.0.3` and `redis` to `172.18.0.2`, but TCP probes to ports 5432 and 6379 time out. PostgreSQL's own `pg_isready` works from inside the database container. Redis answers locally with `NOAUTH Authentication required`, showing that its listener answers and authentication is required.
- **Network recreation test:** `docker compose down --remove-orphans` followed by `docker compose up -d db redis` recreated the network and containers, but the cross-container TCP timeouts remained. No `-v` flag was used; the named database volume was preserved.
- **Built-in bridge comparison:** Connecting the same PostgreSQL and Redis containers to Docker's built-in `bridge` and testing their bridge IPs from `afcon360-web` succeeded for both TCP ports (exit code 0).
- **What this establishes:** A path-specific connectivity difference is reproducible: the default built-in bridge path succeeded, while the Compose user-defined bridge path timed out in this Codespaces Docker environment.
- **What is not yet established:** The underlying cause of that difference. Do not call it a confirmed Codespaces platform defect until network settings, routes/firewall behavior, and repeatability are inspected.
- **Temporary workaround:** Additional built-in bridge attachment proved direct IP reachability. This is diagnostic evidence only, not an approved durable design. Do not bake dynamic container IPs or dependence on the built-in bridge into application configuration.
- **Next investigation:** Capture `docker info`, both network inspections (driver/options/subnets/IPAM), container routes and listeners, and compare connectivity from each side. Then decide whether the durable fix belongs in the sandbox/Compose network design or the chosen replay environment. Prefer stable service-name connectivity; avoid hard-coded container IPs.
- **Status:** Root cause OPEN; full application startup must stay gated.

### RPL-05 — Web startup was blocked before Alembic began

- **Observed:** `docker-entrypoint.sh` repeatedly printed `db:5432 - no response` while waiting for PostgreSQL. The web container later exited with code 137 and `OOMKilled=false`. The `alembic_version` relation was absent when queried.
- **Interpretation:** The logs do not show a completed migration or an Alembic migration exception. The missing table is consistent with startup being blocked before the migration command ran successfully.
- **Unresolved:** Exit code 137 indicates the process was killed, but the cause is unknown; `OOMKilled=false` means we must not label it an OOM event without further evidence.
- **Next step:** Resolve the Compose-network connectivity issue first. Then launch web once with observable logs and diagnose any subsequent migration error on its own merits.
- **Status:** Replay not started/verified; application health not tested successfully.

### RPL-06 — Alpine locale warning during fresh PostgreSQL initialization

- **Observed:** PostgreSQL logs included `sh: locale: not found` and `WARNING: no usable system locales were found`, followed by successful initialization and healthy status. Compose passes `--locale=en_US.UTF-8`.
- **Interpretation:** This warning did not prevent the database from becoming healthy, but the intended locale behavior has not been verified.
- **Next step:** Confirm the effective database locale/collation and decide whether Alpine's locale behavior is acceptable for replay and production-parity requirements. Do not silently remove locale flags or change collation assumptions without evidence.
- **Status:** Non-blocking observation; follow-up required before calling locale parity verified.

## Current evidence-based state

| Gate | Result |
|---|---|
| Compose configuration parses | PASS |
| Python 3.13 application image builds | PASS |
| H3-A compatibility helper regression tests | PASS — 9 passed |
| PostgreSQL 18.6 service healthy | PASS |
| Redis service healthy | PASS |
| Compose service-name DNS resolution from app image | PASS |
| TCP to PostgreSQL/Redis over Compose network | FAIL — timeout |
| TCP to PostgreSQL/Redis over built-in bridge IPs | PASS — diagnostic comparison only |
| Active Alembic chain reaches `1793013676` | NOT VERIFIED |
| Fresh database/schema checks after full replay | NOT RUN |
| App health endpoint | NOT VERIFIED |

## Rules for continuing the investigation

1. Do not edit `main`; keep all investigation changes on the sandbox branch until gates and review are complete.
2. Do not treat a workaround as a root-cause fix. Label each explicitly.
3. Never use `docker compose down -v`, volume deletion, production databases, or production commands during this disposable replay.
4. After each new failure, preserve the exact command, exit status, relevant logs, commit SHA, environment/server version, and whether migrations had begun.
5. Fix environmental prerequisites before interpreting blocked migration execution as a migration defect.
6. After the first clean replay, turn the proven manual steps into a repeatable script or CI job. It should fail fast on connectivity/runtime errors, capture the exact Alembic head and schema checks, and never silently reset or delete persistent volumes.
