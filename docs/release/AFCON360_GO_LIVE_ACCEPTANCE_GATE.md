# AFCON360 Go-Live Acceptance Gate

**Current verdict: NOT APPROVED FOR PRODUCTION RELEASE**

This record distinguishes repository evidence from production evidence. A green CI run is necessary, but it is not a production restore test, live-server verification, payment-provider sandbox test, or regulatory approval.

Last operator-provided production snapshot in the release review:
- Oracle host: `afcon-360`, Ubuntu 24.04.4.
- Production checkout: `8c25246ab5e41d44f0d64ad9ff030819e69e9ff1`.
- PostgreSQL container: `afcon360_db`, PostgreSQL 15, reported healthy.
- Redis container: `afcon360_redis`, Redis 7, reported healthy.
- Web container: `afcon360_web`, reported healthy, bound to `127.0.0.1:5000`.
- `pg_dump 15.19` is installed in the observed database container.
- Server checkout contains untracked `.env.docker.runtime`, `.env.runtime`, and `docker-compose.prod.yml`. Preserve these files; never clean or overwrite them.
- An additional container named `musing_rosalind` was reported unhealthy and has not yet been identified.

These facts are historical operator output, not a current live verification. Re-run the read-only checks immediately before release.

## Gate status

| Gate | Required acceptance evidence | Current disposition |
|---|---|---|
| Exact release commit | CI and review attached to the exact candidate commit; candidate is merged to the intended release branch | OPEN — PR #15 is still a draft |
| PostgreSQL compatibility | Disposable migration replay and regression suite on PostgreSQL 15 and 18 | IN PROGRESS — matrix is configured; latest run must finish successfully |
| Wallet regression | Ledger, concurrency, refunds, payouts, withdrawals, payment identity and reconciliation tests run; all skips and failures reviewed | IN PROGRESS — broader `tests/wallet/` suite has been added to CI |
| Redis runtime | Real Redis connection, server-side session persistence, shared rate limits, Celery broker connection and Socket.IO Redis manager/emit checked | IN PROGRESS — dedicated CI smoke script and Redis service added |
| Live database identity | Web container connection metadata matches the actual production database container; live Alembic revision recorded | OPEN — latest read-only server output required |
| Existing database upgrade safety | Production-like copy restored and candidate release/migration rehearsed against that copy | OPEN |
| Backup restore | A backup has been restored into an isolated PostgreSQL 15 database and application-level data checks pass | OPEN — archive listing or successful dump alone is insufficient |
| Rollback rehearsal | Documented rollback executed against the isolated candidate environment, with measured recovery and explicit data-loss boundary | OPEN |
| Redis eviction/memory | Effective live `maxmemory`, `maxmemory-policy`, memory use, evictions, persistence and container limit inspected | OPEN — tracked Compose currently declares `allkeys-lru`; untracked production overlay may override it |
| Owner MFA | Every active platform owner has verified TOTP enrolment; policy toggle and old-session revocation have been tested; live owner recovery path is documented | OPEN — repository tests do not enrol production owners |
| Encryption key continuity | Existing production `ENCRYPTION_KEY` is confirmed present and preserved; encrypted MFA and other secrets can be decrypted by the candidate | OPEN — never replace the key as a troubleshooting step |
| Public end-to-end smoke | HTTPS/Nginx, registration/login, owner MFA, transport quote/accept/match lifecycle, customer notifications and health endpoints verified on candidate deployment | OPEN |
| Financial operations | Payment-provider sandbox, signed webhook handling, idempotency, refund/payout reconciliation, settlement and country-specific legal/compliance approvals documented | OPEN — real-money operations remain disabled |
| Extra container | Purpose, owner, mounts, resources and dependencies of `musing_rosalind` identified | OPEN — do not stop or remove it until identified |

## Non-negotiable data and security protections

1. Never run production migrations until the exact candidate has passed migration replay and an upgrade rehearsal against an isolated copy of the production database.
2. Never use `docker compose down -v`, delete database/Redis volumes, reset production, or clean the server checkout as part of a release.
3. Preserve the live encryption key. Generating a replacement key will make data encrypted with the previous key unreadable unless a separately rehearsed re-encryption process is performed.
4. Keep real-money wallet operations disabled until the broader financial suite, provider sandbox, reconciliation, operational controls and required approvals are complete.
5. Do not treat Redis `PING` as proof that session persistence, rate limiting, Celery or Socket.IO fan-out work. Do not use `allkeys-lru` for a shared Redis instance carrying non-disposable queues or session state without an explicit data-loss decision.
6. A release rollback is not the same as restoring a database backup. Record whether a rollback is code-only, schema-compatible, or requires a separately rehearsed database recovery.

## Required recovery rehearsal

The rehearsal must use a separate database and must not write to the production database.

1. Capture a consistent PostgreSQL custom-format backup using the production PostgreSQL major version and record its size, timestamp, checksum and source database identity.
2. Store the backup outside the production host, protect it with the approved encryption/access controls, and verify that the off-host copy is complete.
3. Create a separate restore target. Restore the backup into it with `pg_restore`; do not restore over production.
4. Verify the restored server version, Alembic revision, schema inventory, key business-table row counts, selected account/ledger totals, users and organisation records. Compare against the source snapshot using read-only queries.
5. Point an isolated candidate application at the restored database and verify startup, login, owner MFA decryption, transport read paths and wallet read-only balance derivation.
6. Rehearse returning the isolated candidate to the previous application image and document whether any schema changes would prevent that rollback.
7. Record commands, operator, start/end times, checksums, result, exceptions and recovery duration. A backup is accepted only after this restore succeeds.

## Required pre-release production inspection

Run only read-only commands first. Confirm:
- the latest remote main SHA and production checkout SHA;
- the web container's effective database host/database name and PostgreSQL container identity;
- both `docker compose ... config --services` and the effective Redis service configuration, without printing environment values;
- PostgreSQL version and live Alembic revision;
- Redis memory limit, `maxmemory`, `maxmemory-policy`, used memory and evicted-key count;
- session backend, rate-limit backend and Socket.IO manager mode;
- the unhealthy extra container's Compose labels, image, mounts and role;
- available disk space and backup destination.

Do not paste secrets, passwords, full connection strings, TOTP seeds, backup codes or environment-file contents into reports or chat.

## Release sequence after all gates pass

1. Freeze a specific candidate commit and container image digest. Record the currently running image and commit for rollback.
2. Take and verify the off-host backup. Confirm the isolated restore has passed.
3. Apply only the reviewed deployment configuration. Preserve server-only environment and Compose files.
4. Apply a migration only if the candidate has an approved migration and its production-like rehearsal has passed.
5. Perform controlled deployment and verify startup, readiness, login/MFA, transport smoke and logs.
6. Keep real-money wallet operations disabled until their separate provider, reconciliation and compliance gates pass.
7. Monitor error rates, database pool, Redis memory/evictions, queue depth, Celery failures and Socket.IO reconnects. Retain the rollback image and recovery backup.

**Current decision remains: NO-GO.** Move this record to GO only when every release-blocking gate above has evidence attached and reviewed. CI success alone cannot change the decision.
