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

### RPL-04 — Container TCP connectivity differs by source network in Codespaces

- **Observed services:** PostgreSQL and Redis both report healthy. PostgreSQL accepts `pg_isready` against its own loopback and service address from inside its own container. Redis responds locally with `NOAUTH Authentication required`, showing the listener answers and authentication is required. A PostgreSQL-container probe to Redis times out.
- **Compose network:** Inspection reports a normal user-defined bridge named `afcon360_afcon_net`, subnet `172.18.0.0/16`, gateway `172.18.0.1`, no custom network options. DNS from a temporary app-image container resolves `db` to `172.18.0.3` and `redis` to `172.18.0.2`; TCP to either service times out. Recreating Compose containers/network did not cure the symptom, and the existing named database volume was preserved (no `-v` was used).
- **Built-in bridge network:** Docker's built-in `bridge` uses `172.17.0.0/16`; its inspection shows the usual default bridge options, including inter-container connectivity enabled. PostgreSQL and Redis were additionally attached to this bridge at `172.17.0.2` and `172.17.0.3`.
- **Successful test, with its scope:** A standalone temporary app-image container explicitly started with `docker run --network bridge` successfully made TCP connections to the PostgreSQL and Redis built-in-bridge IP addresses (exit code 0).
- **Follow-up matrix from a Compose-network source:** A `docker compose run` temporary app-image container on the Compose network timed out for all four destinations: PostgreSQL Compose IP `172.18.0.3:5432`, PostgreSQL built-in bridge IP `172.17.0.2:5432`, Redis Compose IP `172.18.0.2:6379`, and Redis built-in bridge IP `172.17.0.3:6379`.
- **Interpretation correction:** These results are not contradictory. The successful test's *source container* was on the built-in bridge; the follow-up matrix's source container was on the Compose network. The evidence shows built-in-bridge source -> built-in-bridge destination works, while Compose-network source cannot reach either service in this environment. A connection across two different bridge networks would normally be isolated, so the cross-network matrix entries alone are not evidence of a defect. The same-network Compose TCP timeouts are the abnormal part that remains to explain.
- **Environment:** `docker info` reports Docker Server `29.8.0-1`, Ubuntu `24.04.5 LTS (containerized)`. The Compose network has no non-default options. This is consistent with a nested/containerized Docker environment, but these facts alone do not prove the underlying cause.
- **External corroboration (hypothesis, not proof):** A [GitHub Codespaces community discussion #208098](https://github.com/orgs/community/discussions/208098) describes a closely similar signature—containerized Ubuntu, working DNS, and TCP timeouts on a user-defined bridge—and proposes nested Docker bridge/forwarding behavior as a cause. This is an independent community report, not authoritative confirmation that the same cause applies here. [Docker's bridge documentation](https://docs.docker.com/engine/network/drivers/bridge/) states that containers attached to the same bridge should communicate by default and that different bridge networks are isolated.
- **Temporary workaround status:** Built-in-bridge connectivity is proven only for a source container attached to that built-in bridge and destination IPs on that bridge. It is not yet a safe application workaround because the Compose source cannot reach it, and service-name discovery differs on the default bridge. Do not embed dynamic IPs into application configuration or declare the networking issue fixed.
- **Next investigation:** Inspect `docker info` networking/forwarding and userland-proxy settings, routes, and listeners. Then test a documented host-published-port/host-gateway path or a replay topology supported by this environment, without exposing DB/Redis beyond the sandbox. If the limitation is specific to nested Codespaces networking, document the environment requirement or use a suitable replay runner. Preserve stable service discovery and do not change application/migration logic to mask network timeouts.
- **Status:** Compose same-network connectivity root cause OPEN; web startup and migration replay stay gated.

### RPL-07 — Published-port probe command rejected before the network test ran

- **Observed:** A temporary HTTP server container started successfully on the built-in bridge with a port published on `172.17.0.1:18089`. The subsequent `docker compose run ... --add-host=host.docker.internal:host-gateway` command returned `unknown flag: --add-host` before the probe process ran. The test wrapper then removed the temporary server. PostgreSQL and Redis remained healthy.
- **Interpretation:** This is a Compose CLI/option compatibility problem, not a failed TCP test. It provides no evidence for or against host-gateway connectivity. Do not record the published-port approach as failed.
- **Next step:** Repeat the same isolated HTTP probe using `docker run --network afcon360_afcon_net --add-host=host.docker.internal:host-gateway` directly, bypassing the Compose `run` command. Keep the temporary port bound only to the Docker bridge gateway and remove the probe container on completion.
- **Status:** Probe not yet executed; root networking issue remains open.

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

### RPL-08 — Terminal/session expiry interrupted the published-port probe

- **Observed:** The user reported that the Codespaces terminal expired before the published-port test result could be captured. The prior test had created a temporary HTTP probe container and used a shell cleanup trap; an earlier run confirmed the cleanup command removed the probe container. The most recent attempted command's outcome is unknown, so it must not be classified as a network failure or PASS.
- **Impact:** Manual interactive testing is vulnerable to terminal/Codespace lifecycle interruption, and the current networking question remains unresolved. Codespaces documentation notes that stopped/timed-out Codespaces stop running processes while saved workspace changes remain available after restarting.
- **Durable process improvement:** Prefer a bounded diagnostic script with explicit timeouts, output capture, and cleanup, then move the full fresh-database replay to a repeatable CI job or another Docker host with verified inter-container networking. Avoid long, manually pasted loops as the only record of a test.
- **Recovery:** Reopen the existing Codespace rather than creating a new one if possible, use a new terminal, check the investigation branch and `docker compose ps -a`, then run only the next diagnostic if this environment is still in use. Do not assume containers survived a Codespace stop.
- **Status:** Published-port probe NOT CONFIRMED; terminal expiry is an execution-process hurdle, not a networking result.

### RPL-09 — CI image excludes tests by design; initial workflow invoked tests from wrong path

- **Observed:** The first hosted GitHub Actions run successfully validated Compose and built the app image. The regression-test step then reported `no tests ran` and `ERROR: file or directory not found: tests/test_h3_baseline_pg_version_compat.py`; the run stopped before starting PostgreSQL/Redis or running migrations.
- **Root cause confirmed from `.dockerignore`:** It intentionally excludes the entire `tests/` directory, as well as Markdown and Docker files, from the production image build context. Therefore this was a CI test invocation mistake, not a missing source test and not a test assertion failure.
- **Correction committed:** Workflow commit `171ba7771113b2ede2213c42e63451797b7830d8` mounts the checked-out workspace read-only at `/workspace` for the test step and runs pytest from that mounted source. The production image continues to exclude tests.
- **Verification in progress:** A second GitHub Actions run has started for commit `171ba7771113b2ede2213c42e63451797b7830d8`; its final outcome must be recorded separately.
- **Status:** Initial workflow wiring defect diagnosed; corrected attempt pending. No migration has been reported from the first run.

### RPL-10 — Production configuration requires ENCRYPTION_KEY before Alembic can run

- **Observed on hosted runner:** After correcting the test-source mount, the image built, the H3-A compatibility tests passed, PostgreSQL and Redis started healthy, and the web entrypoint successfully reached both services. The web container then failed while Flask loaded configuration, raising `RuntimeError: [CONFIG] FATAL: Missing required production environment variables: ENCRYPTION_KEY`.
- **Boundary confirmed:** `docker-entrypoint.sh`'s early four-variable check passed, but `app/config.py::validate_for_production()` has an additional required `ENCRYPTION_KEY` check because the Docker image sets `FLASK_ENV=production`. Thus the startup had progressed to application configuration but had not successfully run `flask db upgrade`. The `alembic_version` table was absent, consistent with migration not having begun successfully.
- **Correction committed:** Workflow commit `f727d92e60e6a004a59597e5da7985f1e5771bcd` adds a cryptographically random, per-run dummy `ENCRYPTION_KEY` to the ephemeral `.env`/`.env.docker`. It is not a real application/production secret and is not committed to the repository.
- **Additional observation:** App startup logs say `.env` and `.env.docker` files are not present inside `/app`; Compose passes their variables as container environment, which the early checks could see. This message is currently informational in this run, but after the required-key correction the next run should show whether config initialization works with environment variables alone. Do not add env files into the production image to suppress these messages without verifying the intended config loader contract.
- **Verification:** A third hosted-runner replay has been triggered by the workflow correction; outcome pending. No successful Alembic replay has yet been recorded.
- **Status:** Missing test-only production configuration corrected in CI; migration gate still open.

### RPL-11 — The migration chain passed; a diagnostic collation query failed

- **Observed:** Hosted runner commit `f727d92e60e6a004a59597e5da7985f1e5771bcd` passed the image build and the 9 H3-A compatibility regression tests. Web startup connected to PostgreSQL and Redis, then log output confirmed each active Alembic upgrade:
  ` -> h3a20261020 -> c076b257b11d -> 1792869659 -> d3ba8c51f407 -> 1793011323 -> 1793013676`.
  The workflow emitted `✅ Migrations complete`; a direct database query returned `ALEMBIC_REVISION=1793013676`.
- **Why the overall job failed:** The subsequent environment verification tried `current_setting('lc_collate')` and PostgreSQL returned `unrecognized configuration parameter "lc_collate"`. The migration had already succeeded; the job stopped before the schema-count and health checks because the diagnostic SQL was wrong.
- **Correction committed:** Workflow commit `9c9d15b5e34a0a5cdc0c6029c89237b9c9a3a571` reads collation from `pg_catalog.pg_database.datcollate/datctype`, while `server_encoding` remains read via `current_setting()`.
- **Additional observable startup behavior:** During Flask app initialization against the empty database, PostgreSQL logged an error for a query to the not-yet-created `system_configs` table (`CSP_STRICT_ENFORCE`). Source inspection of `app/__init__.py::refresh_csp_strict_cache()` confirms this pre-baseline condition is explicitly handled: the lookup is best-effort, failures roll back the SQLAlchemy session, and the flag fails closed to `False`. This is intentional/non-fatal for the fresh replay, though the emitted database ERROR may warrant a separate logging-noise review. Do not change CSP policy behavior as part of replay work.
- **Status:** Full active Alembic chain and head revision PASS on the hosted runner. Schema count/collation reporting and HTTP health check remain pending after correcting the verification query; complete deployment replay not yet PASS.

### RPL-12 — First hosted fresh-database replay PASS (end-to-end)

- **Workflow run:** [GitHub Actions run 40469293373](https://github.com/twikirize/afcon360/actions/runs/40469293373), branch `sandbox/codespaces-alembic-investigation`, workflow source commit `9c9d15b5e34a0a5cdc0c6029c89237b9c9a3a571`.
- **Docker/config gate:** Compose validation PASS; application image build PASS with Dockerfile Python 3.13; only disposable, freshly generated workflow credentials used.
- **Regression tests:** `tests/test_h3_baseline_pg_version_compat.py` — **9 passed**.
- **Service networking:** On hosted GitHub Actions Ubuntu runner, the app container resolved and connected to PostgreSQL and Redis through normal Compose service names. This confirms those Compose settings work on this runner; Codespaces' earlier TCP timeouts remain environment-specific to the tested Codespaces instance.
- **Migration chain:** The normal `docker-entrypoint.sh` / `flask db upgrade` path ran each migration in order:
  `h3a20261020 -> c076b257b11d -> 1792869659 -> d3ba8c51f407 -> 1793011323 -> 1793013676`.
  The log emitted `Migrations complete`; direct SQL verification returned `ALEMBIC_REVISION=1793013676`.
- **Baseline provenance:** The H3-A root migration logged the approved source database `afcon360_h2p_replay_20261018_test`, source revision `df55cbe3f516`, source PostgreSQL `18.4`, and normalized SQL SHA-256 `0701c42dda041f3725c59d2b8081fd4534b5f8d3359f67839aad98c8d53198da`. The target runner server itself is PostgreSQL `18.6`.
- **Database settings reported by PostgreSQL:** database `afcon360_replay_test`; server encoding `UTF8`; `datcollate=en_US.UTF-8`; `datctype=en_US.UTF-8`.
- **Fresh replay counts (public schema):** `pg_tables=226`; public enum types `49`; public check constraints `139`. These are captured as a new comparison point, not yet a schema-parity PASS: reconcile exact catalog counts and object identities against the approved expected schema/reference.
- **Application health:** The public container port's `GET /api/health/ping` eventually returned `{"status":"ok"}` with `APP_HEALTH_HTTP_200=PASS`. Early curl attempts during app startup received connection resets, then the retry loop succeeded; readiness checks should accommodate the actual startup delay.
- **Non-blocking observation:** PostgreSQL logs an Alpine locale warning (`locale: not found`, `no usable system locales were found`) despite reporting the requested locale names in database metadata. Locale/collation behavior is not fully verified by the metadata string alone; retain RPL-06 follow-up.
- **Non-blocking, understood startup behavior:** A `system_configs` lookup for `CSP_STRICT_ENFORCE` emitted an error before the baseline created that table. The source's `refresh_csp_strict_cache()` intentionally catches this, rolls back, and fails closed to `False`; this did not block migration.
- **Overall result:** **PASS for a fresh Docker Compose deployment replay through the expected Alembic head and HTTP health endpoint on the hosted GitHub Actions runner.** This is not yet a full production-parity/schema-parity sign-off, and it does not prove the Codespaces nested Docker network issue is fixed.

### RPL-13 — Repeat replay PASS with structural count guard

- **Workflow run:** [GitHub Actions run 40469733857](https://github.com/twikirize/afcon360/actions/runs/40469733857), workflow commit `f15e7e880bf1c91bc853f2a38c61aa05e4cd159e`, sandbox branch.
- **Repeatability result:** All workflow steps completed successfully on a second fresh hosted-runner environment. The image built; H3-A compatibility tests reported **9 passed**; the normal web startup reported `Migrations complete`; direct SQL returned `ALEMBIC_REVISION=1793013676`; schema-shape checks passed; health endpoint returned `APP_HEALTH_HTTP_200=PASS`; cleanup succeeded.
- **Counts asserted by the workflow:** `PUBLIC_TABLES=226`, `PUBLIC_ENUMS=49`, `PUBLIC_CHECK_CONSTRAINTS=139`, with `SCHEMA_SHAPE_COUNTS=PASS`.
- **Meaning:** The full replay is now repeatable in the hosted GitHub Actions Docker environment across two successful fresh-runner runs, and the recorded coarse schema shape has a regression guard. This supports the deployment replay path, not full object-level schema parity, production-readiness, or the resolution of Codespaces' local Docker connectivity failure.
- **Status:** Second hosted fresh replay **PASS**. Exact approved-schema parity and locale behavior remain separate follow-up gates.

## Current evidence-based state

| Gate | Result |
|---|---|
| Compose configuration parses | PASS |
| Python 3.13 application image builds | PASS |
| H3-A compatibility helper regression tests | PASS — 9 passed |
| PostgreSQL 18.6 service healthy | PASS |
| Redis service healthy | PASS |
| Compose service-name DNS resolution from app image | PASS |
| TCP from Compose-network source to services' Compose IPs in Codespaces | FAIL — timeout |
| TCP from Compose-network source to services' built-in bridge IPs | FAIL — different bridge network; not a same-network test |
| TCP from built-in-bridge source to services' built-in bridge IPs | PASS — source placement matters; diagnostic only |
| TCP to PostgreSQL and Redis through Compose from hosted GitHub Actions runner | PASS — web logs show both service connections succeeded |
| Hosted runner normal app startup | PASS — after CI added a fresh ephemeral `ENCRYPTION_KEY` |
| Active Alembic chain reaches `1793013676` on hosted runner | PASS — migration logs and direct Alembic-version query agree |
| Fresh database schema counts / collation metadata | PASS — 226 public tables, 49 enums, 139 checks; parity comparison pending |
| App health endpoint | PASS — HTTP 200 and `{"status":"ok"}` on hosted runner |

## Rules for continuing the investigation

1. Do not edit `main`; keep all investigation changes on the sandbox branch until gates and review are complete.
2. Do not treat a workaround as a root-cause fix. Label each explicitly.
3. Never use `docker compose down -v`, volume deletion, production databases, or production commands during this disposable replay.
4. After each new failure, preserve the exact command, exit status, relevant logs, commit SHA, environment/server version, and whether migrations had begun.
5. Fix environmental prerequisites before interpreting blocked migration execution as a migration defect.
6. After the first clean replay, turn the proven manual steps into a repeatable script or CI job. It should fail fast on connectivity/runtime errors, capture the exact Alembic head and schema checks, and never silently reset or delete persistent volumes.


## RPL-14 — 27 October checkpoint and register reconciliation

- **Owner's operational checkpoint (corrected):** The owner confirmed that 24 checkpoints were complete before Docker, making the Docker fresh-database replay operational checkpoint **#25**. It is recorded as **PASS for the tested GitHub-hosted Docker environment**.
- **Successful run:** [GitHub Actions 40469733857](https://github.com/twikirize/afcon360/actions/runs/40469733857), workflow commit `f15e7e880bf1c91bc853f2a38c61aa05e4cd159e`; the preceding hosted replay [40469293373](https://github.com/twikirize/afcon360/actions/runs/40469293373) also succeeded.
- **Evidence:** Fresh hosted checkout; Docker image built; 9 H3-A compatibility tests passed; PostgreSQL 18.6 and Redis healthy; normal entrypoint logged `Migrations complete`; Alembic revision verified as `1793013676`; schema guard passed at 226 public tables, 49 enums, 139 CHECK constraints; application health returned HTTP 200 / `{"status":"ok"}`.
- **Safety boundary:** The workflow generated disposable credentials, used a disposable replay database, and cleaned up containers without `docker compose down -v`. It did not modify `afcon360_prod` or `afcon360_test`.
- **Formal 39-item mapping:** Top-level Item 12 remains ADVANCED because a successful fresh replay does not complete the census and revision/catalog evidence for existing environments. Sub-item 12b (Docker census) remains OPEN. Top-level Item 31 remains CLOSED and now has stronger clean-checkout/PostgreSQL 18.6 evidence. Top-level Item 26 remains NOT STARTED because it tests safety when existing data is present; an empty database cannot prove row preservation or populated-state migration safety. The 39-item status totals remain 24 CLOSED, 10 ADVANCED, 1 PARTIAL and 4 NOT STARTED.
- **Scope limit:** This is repeatability evidence for the tested GitHub-hosted PostgreSQL 18.6 Docker workflow. It does not prove PostgreSQL 15 compatibility, exact schema parity, readiness of existing databases, universal compatibility with AWS/Oracle Cloud or other hosting configurations, or resolution of the local Codespaces nested-Docker network timeout.
- **Status:** Operational Docker replay checkpoint PASS (tested environment); wider investigation remains active. See the master register Phase 15 and [plain-language 39-item register](AFCON360_39_ITEM_REGISTER_PLAIN_LANGUAGE.md).



## RPL-15 — 27 October: Codespaces read-only Docker census and empty sandbox database

- **Source:** Owner-pasted terminal output from Codespaces branch sandbox/codespaces-alembic-investigation. These are user-run results, not commands executed by the assistant.
- **Docker engine:** Client/server 29.8.0-1, API 1.56; server OS Ubuntu 24.04.5 LTS (containerized), x86_64, overlayfs. `docker version`, `docker info`, `docker compose ps -a`, `docker ps -a`, volume and network listing succeeded.
- **Visible Compose containers:** afcon360_db (postgres:18-alpine, healthy) and afcon360_redis (redis:7-alpine, healthy). Full `docker ps -a` listed only those two; no web, Nginx, Celery or Celery Beat container was present.
- **Active PostgreSQL mount:** volume afcon360_postgres_data_pg18 at /var/lib/postgresql. The older afcon360_postgres_data volume remains present. No volume was removed.
- **Redis mount/network:** afcon360_redis_data at /data; both containers were attached to afcon360_afcon_net and default bridge in the inspection output. Other volumes included afcon360_app_logs and a hash-named volume whose purpose was not established.
- **Database identity:** afcon360_sandbox / afcon360_sandbox, PostgreSQL 18.6, UTF8, locale metadata en_US.UTF-8. The server lists afcon360_sandbox, postgres, template0 and template1.
- **Schema:** In afcon360_sandbox, only non-system schema public is present; zero public tables, enum types and CHECK constraints; no alembic_version table in any schema. Read-only SQL inspections exited 0. This records an empty, unmigrated local sandbox, not a migration failure. It is not evidence about the separately recorded Production/Test databases.
- **Git working tree:** The owner reported blank `git status --short`, `git diff --name-only` and `git diff --cached --name-only`, on branch sandbox/codespaces-alembic-investigation at local HEAD 2287936. Tracked app/__init__.py, app/config.py and app/realtime.py at that commit contain Socket.IO disabling for one-shot Flask/Alembic CLI invocations. Therefore the previous “uncommitted local change” wording for 12c is stale for this checkout, but source-history and focused-test verification are still needed before 12c is closed.
- **Item 12 outcome:** Top-level Item 12 remains ADVANCED. The old Windows Docker-command-not-found obstacle is resolved for the Codespaces host and local census evidence is now recorded. Remaining work: verify the Socket.IO/CLI change history/tests (12c) and obtain separate read-only revision/catalog evidence for actual deployed environments. Do not start the web container merely to inspect it; its normal entrypoint may run migrations. Do not delete or reset volumes.
- **Status:** Local Codespaces census recorded; broader deployment-state census still in progress.

---

## RPL-16 — 27 October: Socket.IO bare-CLI detector runtime probe and test-coverage gap

- **Source:** Owner-pasted Codespaces terminal output on `sandbox/codespaces-alembic-investigation`. These were run by the owner, not executed by the assistant in Codespaces.
- **Execution boundary:** Temporary Compose one-off containers used `--rm --no-deps`, Python as entrypoint, and the repository mounted read-only at `/workspace:ro`. The web service was not started, and the commands did not invoke the migration entrypoint or issue SQL. No database change was reported.
- **Coverage search:** `GIT_PAGER=cat git grep -n -I -E 'is_bare_cli_invocation|_resolve_socketio_enabled' -- tests` returned exit 1 with no matches. That is a no-match result, not a failed runtime test.
- **Manual detector probe:** six of six cases matched expected values, with `CLI_DETECTOR_FAILURES=0` and `CLI_DETECTOR_EXIT=0`: Flask db upgrade = True; Flask db current = True; Flask run = False; Python -m Flask db upgrade = True; Python -m Alembic upgrade = True; Gunicorn server = False.
- **Existing queue suite:** `tests/test_socketio_queue_contract.py` reported **6 passed in 3.05s**, `QUEUE_TEST_EXIT=0`.
- **Related-but-not-equivalent coverage:** the supplied test search showed a production-console test that sets `SOCKETIO_ENABLED=False` and verifies persistence remains independent. It does not directly test the CLI detector or `_resolve_socketio_enabled`.
- **Conclusion:** implementation runtime behavior is supported for these six simulated command lines, and the existing queue-contract suite passes. Dedicated persistent tests for the CLI detector/application enablement decision were not found. Keep sub-item 12c IN REVIEW; add direct automated tests and run them in read-only/no-database mode before closure. Top-level Item 12 remains ADVANCED pending both 12c and actual deployed-environment revision/catalog evidence.
- **Safety:** no source, test, migration, database row, schema, or Docker volume was changed in this checkpoint.


---

## RPL-17 — 27 October: Item 12c history audit and permanent CLI regression tests added

- **Source-history evidence:** Commit `bd289acc238eb17d82bf4f55c6e451e53752d0f3` (22 October) added `app/realtime.py` and modified `app/__init__.py` and `app/config.py`. Commit `7b65c4c33b911532ec42f5d6ef10d8a8a2e491a3` (26 October) modified `app/__init__.py`, added `tests/test_socketio_queue_contract.py`, and extended `tests/test_production_console.py`.
- **Coverage finding:** Existing queue-contract tests and the production-console persistence test are related but do not directly cover `is_bare_cli_invocation` or `_resolve_socketio_enabled`.
- **Test file added:** [`tests/test_realtime_cli_detection.py`](https://github.com/twikirize/afcon360/blob/sandbox/codespaces-alembic-investigation/tests/test_realtime_cli_detection.py), commit `e8af03d8713a6ce0a6ce4449249052bf23559440`. It contains 28 focused cases covering command-line classifications, `sys.orig_argv` preference/fallback, CLI-forced Socket.IO disablement, and non-CLI environment flag behavior.
- **Run status:** Not yet executed in the submitted evidence. Do not describe the new tests as passing until the owner runs them and provides the pytest summary and exit code.
- **Next command after syncing the investigation branch in Codespaces:**

```bash
docker compose run --rm --no-deps -T \
  -v "$PWD:/workspace:ro" \
  -w /workspace \
  --entrypoint python web \
  -m pytest --noconftest -q -p no:cacheprovider \
  tests/test_realtime_cli_detection.py \
  tests/test_socketio_queue_contract.py
```

- **Safety:** This is a temporary no-dependency one-off test container with the source mounted read-only. It does not start the normal web entrypoint and must not run migrations or touch database rows. No Docker networking override was introduced; no app source, migration or database configuration was changed.
- **Disposition:** 12c remains IN REVIEW pending actual regression results. Parent Item 12 remains ADVANCED and still requires read-only revision/catalog evidence for the actual deployed environments.


---

## RPL-18 — 27 October: focused Item 12c CLI/Socket.IO tests passed

- **Branch sync:** Owner reported a clean `git status --short`, successful `git fetch origin`, and successful `git merge --ff-only origin/sandbox/codespaces-alembic-investigation`. The new test file arrived in that fast-forward; no merge conflict was reported.
- **Command:** `docker compose run --rm --no-deps -T -v "$PWD:/workspace:ro" -w /workspace --entrypoint python web -m pytest --noconftest -q -p no:cacheprovider tests/test_realtime_cli_detection.py tests/test_socketio_queue_contract.py`
- **Observed result:** `34 passed in 3.14s`; `SOCKETIO_CLI_TEST_EXIT=0`.
- **Scope:** 28 cases from the new direct CLI/resolver regression file plus the 6 existing Socket.IO queue-contract tests. This complements the source-history evidence that commit `bd289acc238eb17d82bf4f55c6e451e53752d0f3` introduced the implementation and commit `7b65c4c33b911532ec42f5d6ef10d8a8a2e491a3` added the earlier queue tests.
- **Execution boundary:** A disposable `--no-deps` test container used the source mounted read-only. Python/pytest replaced the normal entrypoint. No web app startup, Alembic command, database query/write, Docker network change, or volume deletion was part of this run.
- **Disposition:** Sub-item 12c **CLOSED**. Parent Item 12 remains **ADVANCED** pending read-only migration revision/catalog evidence for actual deployed environments. Official 39-item totals are unchanged because 12c is subordinate.


---

## RPL-19 — 27 October: read-only Windows PostgreSQL census for local Production/Test databases

**Evidence source.** Owner-pasted PowerShell output from `C:\Users\OBED\Desktop\afcon360_app`. The command used PostgreSQL 18's local `psql.exe`, selected `localhost:5432` (server address reported as `::1/128`), role `israeli`, and explicitly queried only `afcon360_prod` and `afcon360_test`. The Python wrapper refused a non-local host and refused populated password environment variables or a password-bearing `DATABASE_URL`. Output did not reveal a secret or connection URL.

### Observed result

| Measurement | `afcon360_prod` | `afcon360_test` |
|---|---|---|
| Database / effective role | `afcon360_prod` / `israeli` | `afcon360_test` / `israeli` |
| PostgreSQL endpoint | local IPv6 loopback `::1/128:5432` | local IPv6 loopback `::1/128:5432` |
| Server version | `18.4` | `18.4` |
| Transaction read-only indicator | `on` | `on` |
| Encoding | `UTF8` | `UTF8` |
| Collation / ctype | `English_United Arab Emirates.1252` / `English_United Arab Emirates.1252` | same |
| Public tables | `226` | `226` |
| Public enum types | `49` | `49` |
| Public CHECK constraints | `139` | `139` |
| Public foreign-key constraints | `410` | `410` |
| Installed extensions returned by `pg_extension` | `plpgsql` only | `plpgsql` only |
| Alembic revision | `1793013676` | `1793013676` |
| `psql` exit code | `0` | `0` |

The wrapper reported `READ_ONLY_CENSUS_EXIT=0`. Its SQL used `BEGIN READ ONLY`, set `default_transaction_read_only=on` through `PGOPTIONS`, and ended with `ROLLBACK`. No migration or data-changing command was invoked by this census.

### Reconciliation notes — do not silently overwrite historical evidence

1. **Revision update:** The current local databases report `1793013676`, whereas the older normalized-schema evidence recorded both at `df55cbe3f516`. The older files remain valid as dated historical snapshots, but they no longer establish the current migration revision.
2. **Counts changed from the historical comparison:** The older snapshots recorded 224 public tables, 68 enums in Prod / 49 in Test, and 411 FKs per database in the earlier physical inventory. This census reports 226 / 49 / 410 for each database. Treat these as a changed observation requiring explanation; do not infer exact parity from equal counts.
3. **Extension discrepancy:** Older evidence recorded `pgcrypto` in Prod only, with extension-backed routines and deletion-guard dependencies discussed in the prior review. The current `pg_extension` query reports only `plpgsql` in both databases. Establish whether and when `pgcrypto` and its dependent routines changed before deciding the status of the older dependency record. Do not install, drop, recreate or otherwise mutate an extension as part of this investigation.
4. **Equal migration revisions/counts are not schema identity:** this query measured selected catalog counts, the Alembic version and extension names. It did not compare every table/column/default/index/constraint/function/trigger, data contents or application behavior.
5. **Environment boundary:** This is evidence for two databases on the owner's Windows machine via `localhost`, not proof of the PostgreSQL endpoint used by the remote public website or any other hosting deployment. That remote target must be identified and verified separately through its approved read-only access path.

### Disposition

- **Local Windows Production/Test census: PASS — read-only identity/revision/coarse-catalog queries completed.**
- **Top-level Item 12: remains ADVANCED.** The local databases' current revision/catalog snapshot is now captured, but it does not by itself verify the remote public deployment, and the old-to-current schema/extension/FK discrepancies need explicit reconciliation.
- **Next safe step:** collect a more detailed read-only inventory of the two local databases and compare object definitions/dependencies to the existing historical evidence; separately establish the remote deployment's approved database identity/revision query path. No write or migration is authorized by this finding.

---

## RPL-20 — 27 October: normalized schema-only comparison of local Windows Production/Test databases

**Evidence source.** Owner-pasted PowerShell output from the local comparison under `C:\\Users\\OBED\\Desktop\\afcon360_app`. Both PostgreSQL 18.4 `pg_dump` schema-only exports completed successfully against `localhost:5432` as role `israeli`; both reported exit code `0`. The export used `--schema-only`, `--no-owner`, `--no-privileges`, `--quote-all-identifiers`, and `--exclude-table=public.alembic_version`, with `PGOPTIONS=...default_transaction_read_only=on`. Output files were written under the local temporary directory. No migration or database-changing command was run.

### Raw exports

| Measurement | Production | Test |
|---|---:|---:|
| Raw dump size | 891,210 bytes | 891,320 bytes |
| Raw SHA-256 | `70018DF072205B4B82178A9390EAE9831D97EBAE2064AEEADDF5863760992772` | `D5BBD4A860C7F61F7E80F494AE412E3710E18F64D7D86B7C4B7B1FE4DBDEF167` |
| `pg_dump` exit code | `0` | `0` |

The initial raw diff contained different per-run `\\restrict` / `\\unrestrict` tokens and an extra non-executing comment block stating that the Test dump was not creating the `public` schema because `initdb` creates it. The visible initial diff showed no altered object definition, but the raw files were not identical.

### Normalized comparison

The follow-up local Python comparison removed only the identified run-specific restriction-token lines and the exact non-executing public-schema comment block, and normalized repeated blank lines. It then compared the complete normalized dump text.

- Normalized Production SHA-256: `bb7867e852d77fa210ec5d723caf26af4376b774b129a066899221c1907f2ea1`
- Normalized Test SHA-256: `bb7867e852d77fa210ec5d723caf26af4376b774b129a066899221c1907f2ea1`
- `PROD_TEST_NORMALIZED_SCHEMA_MATCH=YES`
- `DIFF_LINES=0`
- Normalized comparison script exit status: successful; no exception reported.

### Interpretation and boundaries

- **Supported conclusion:** The normalized schema-only dump contents for the two named local Windows databases are identical within this export scope.
- The comparison explicitly excluded `public.alembic_version`; owner and privilege metadata were also excluded. It did not compare table data or prove equivalent runtime/application behavior.
- This is evidence for databases reached through local Windows `localhost:5432` only. It does not establish which database backs the remote public website at `pamoja.space`.
- This current match is more specific than the earlier coarse counts, but it does not by itself reconcile historical catalog/extension observations or verify the remote deployment.

### Disposition

- **Local Windows Production/Test normalized schema comparison: PASS within the stated dump scope.**
- **Top-level Item 12: remains ADVANCED.** The remote deployed database identity/revision still requires its approved read-only verification path; historical evidence also remains subject to reconciliation. Do not change the human-maintained master register from this entry, and do not perform a schema/data write, migration, or extension mutation based on this result.
