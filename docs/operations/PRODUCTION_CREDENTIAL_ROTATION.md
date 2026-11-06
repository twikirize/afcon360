# AFCON360 production credential rotation runbook

**Status:** Procedure only. No credentials are stored here and no live rotation is performed by this document.

This runbook covers the previously exposed PostgreSQL and Redis credentials used by the two-server AFCON360 deployment. Rotation must be coordinated because Server 1 hosts PostgreSQL/Redis and Server 2 connects to both over the private network.

## Non-negotiable safeguards

- Never put credentials in Git, chat, screenshots, command-line arguments, or logs.
- Generate independent, long random passwords and store them in the approved password manager.
- Do not use `docker compose down -v`; do not remove or recreate PostgreSQL or Redis data volumes.
- Do not rotate either credential until a current database backup has completed and its integrity has been checked. Prefer an off-host verified copy and a restore drill before the maintenance window.
- Keep the existing app containers and previous values available only in the protected operator password manager until the new credentials have been proven. Do not write old or new values into a deployment transcript.
- A password change at the database or Redis process does not update existing application container environment variables. Every client must be updated and recreated deliberately.

## Phase 0 — map the live configuration (read-only)

On **Server 1**, identify the actual Compose inputs used for the live services. On **Server 2**, inspect its server-local `docker-compose.worker.yml` and its `env_file` entries. Do not replace or commit that untracked file.

For each of `afcon360_web`, `afcon360_worker`, and `afcon360_beat`, record only whether these variable names are present and non-empty:

- PostgreSQL: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASS`, `DATABASE_URL`
- Redis: `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`

Also identify the protected host-side files that supply those values. The database container's `POSTGRES_PASSWORD` is an initialization setting: changing the Compose environment value alone does **not** change the password of an already-initialized PostgreSQL role.

Never use plain `docker inspect` output in a transcript because it includes full environment values. Use a presence-only awk filter and report only `SET`, `EMPTY`, or `MISSING`.

## Phase 1 — prove recoverability

1. Confirm the latest Server 1 PostgreSQL backup completed and has a recorded size and SHA-256 checksum.
2. Confirm the local backup directory is on persistent storage, not only the container writable layer.
3. Prefer a verified OCI off-site copy once Workstream 5 is operational.
4. Perform a restore test to a disposable database if a current restore proof is not already available.
5. Record the database Alembic revision and container/Compose configuration before the maintenance window.

Do not proceed if the backup/restore path cannot be proven.

## Phase 2 — rotate PostgreSQL password

1. Generate a new dedicated password for the existing application database role. Do not change the role name, grants, ownership, database name, or schema as part of password rotation.
2. Update the protected runtime files on Server 1 and Server 2 so the new password is staged in **all** variables actually consumed by the application (`DB_PASS` and any password-bearing `DATABASE_URL`, for example). Update the Compose interpolation source too, while preserving a record of which service reads each file.
3. In the maintenance window, connect interactively to the existing PostgreSQL instance and use psql's interactive password command for the existing role (for example, `\\password afcon_prod`). Do not put the new password in SQL text, shell history, or a `-c` argument.
4. Recreate only the application clients that open PostgreSQL connections: Server 1 web; Server 2 worker and Beat. PostgreSQL itself does not need a restart for a role password change.
5. Verify fresh connections from Server 1 and Server 2, website health, Celery ping, and one harmless read-only database operation.
6. Confirm the old password no longer authenticates using a protected interactive check. Do not print either password.

If both `DB_PASS` and `DATABASE_URL` are used, updating only one may leave one code path using the old password.

## Phase 3 — rotate Redis password

Redis is the broker/session/cache dependency shared by both hosts. Coordinate the clients and Redis restart in one maintenance window.

1. Generate a new Redis password independent from the PostgreSQL password.
2. Update the protected Server 1 Compose interpolation source and all protected runtime settings on both hosts, including password-bearing Redis URLs (`REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`) and any separately consumed `REDIS_PASSWORD`.
3. Confirm the new Redis endpoint/URL is correctly formed and safely URL-encodes special characters in the password.
4. Gracefully stop Server 2 Beat, then the worker (with a sufficient termination grace period so an active task can finish), and stop Server 1 web. Do not purge or delete any Redis queue, session, or persistence data.
5. Recreate only the Server 1 Redis container with the new protected Compose setting. Preserve its existing Redis data volume. Wait for Redis health.
6. Start Server 1 web with the new settings. Start Server 2 worker and Beat with the new settings.
7. Verify Redis PING from both servers using the new credentials; verify the worker returns Celery `pong`, all three queues are subscribed, Beat is alive, and queue contents are still present as expected.
8. Confirm the old password no longer authenticates through a protected interactive check.

Because Redis is configured with a Compose `--requirepass` command-line setting, an in-memory ACL password change by itself would not be the durable source of truth. The protected Compose/runtime configuration must also be updated before recreating Redis.

## Phase 4 — post-rotation checks

- Server 1 web container is healthy and `/api/health/ping` returns HTTP 200.
- PostgreSQL reports healthy; `afcon360_prod` remains at the recorded Alembic revision.
- Redis reports healthy and its persisted data/queues were not flushed.
- Server 2 worker ping returns `pong`; active queues are `default`, `critical`, and `bulk`.
- Server 2 Beat is running and not repeatedly restarting.
- A harmless task can be sent from Server 1 and observed completing on Server 2.
- No old credential is still present in active container environment variables or protected Compose files.
- Old credentials are revoked and retained nowhere except any approved secure rotation audit record.

## Rollback boundary

Do not roll back by restoring old secrets into chat, Git, or a deployment transcript. If the new credentials fail, keep the affected application clients stopped or in a controlled degraded state, use the approved password manager to reconcile the intended values, and restore service by correcting the protected runtime files and database/Redis authentication state. Never delete volumes or recreate the database as a password-rotation workaround.

## Operator evidence to retain

Record only timestamps, host/container names, variable names with SET/EMPTY/MISSING status, health results, database revision, queue counts, and task IDs. Never record password values, full connection URLs, OTPs, or raw `docker inspect` environment output.
