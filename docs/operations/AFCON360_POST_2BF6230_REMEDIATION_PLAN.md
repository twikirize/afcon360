# AFCON360 production remediation plan — post-2bf6230

**Status:** Planning only. This file records the remediation sequence; it does not change application code, production configuration, secrets, databases, Redis, containers, or infrastructure.

**Baseline:** `main` at `2bf62300f5feb0bce41a887df9a21712c3e8b4b4` (5 November 2026).

## 1. Confirmed baseline and evidence

- Server 1 website, PostgreSQL, and Redis were healthy after release `2bf6230`.
- Server 2 worker and Beat run the same image revision. The worker answered Celery ping and subscribed to `default`, `critical`, and `bulk`.
- Explicit test tasks completed successfully on all three queues: `events.health_snapshot`, `wallet.process_webhook_events`, and `notifications.cleanup_old`.
- At least one scheduled task, `accommodation.cleanup_expired_holds`, returned an error dictionary containing “Working outside of application context” while Celery recorded the task as `succeeded`. This is both an app-context defect and a task-result observability defect.
- Production `auth_configurations.email_verification_required` was `false`; therefore a normal signup did not request a verification email. Server 1 had SMTP variables present in its container environment. Server 2 logs reported `MAIL_USERNAME` and `MAIL_PASSWORD` missing.
- The current code path in `app/notifications/channel_handlers/email.py` uses Flask-Mail/SMTP. A missing `SENDGRID_API_KEY` is not, by itself, proof that this SMTP path cannot send.
- Server 2 is a 1 GiB-class host running one Celery execution slot. The reported 8.7-second `transport.scheduled_booking_dispatch` runtime is a signal to measure, not enough by itself to justify weakening a dispatch-latency guarantee.
- The existing backup service creates local database, files, and configuration backups and calculates checksums. No off-server Object Storage upload path was found in that service.

## 2. Workstreams and planned changes

### A. Celery Flask application context and task outcome correctness — code

**Problem:** `make_celery(app=None)` only installs `ContextTask` when an app is passed, but the module-level instance is created with `make_celery()`. Some task modules compensate with their own context helpers; `app/tasks/cleanup.py` does not. Other task modules create their own app contexts. A task that catches an exception and returns an error dictionary is counted by Celery as successful.

**Plan:**
1. Map every registered Celery task, task decorator/app instance, Flask extension access, and existing app-context helper before changing the factory. Include the separate Celery instance in `app/events/tasks.py` in the registry audit.
2. Implement one consistent, lazy Flask-context task base for the primary Celery app. Do not eagerly call `create_app()` at import time until the app-factory/import graph proves that safe; avoid circular imports and repeated app construction.
3. Preserve existing task names, queues, retry policies, task binding, idempotency, and task registration. Reuse the active context where one already exists.
4. Change `cleanup_expired_holds` so genuine failures are recorded as Celery failures (or explicit bounded retries where safe), not `SUCCESS` with an `error` field.
5. Audit other DB-touching tasks for the same “success with error payload” pattern; fix only confirmed instances.

**Verification gate:** focused tests prove a worker-invoked DB task has Flask app context; tasks with an existing context do not create a second app; expected task names/routes remain registered; retry and bound-task behavior is preserved; the cleanup task no longer reports a context exception as success. Run the focused PostgreSQL/Celery tests and CI before building a release image.

### B. Transactional email and signup verification — code plus runtime configuration

**Problem:** signup verification is disabled in production. In addition, the worker lacks SMTP username/password variables, so asynchronous email delivery cannot be relied upon there.

**Plan:**
1. Use the existing Server 1 SMTP configuration as the starting point. Run a controlled test message from the production website to an explicitly chosen test mailbox; verify provider acceptance and inbox arrival. Do not print or paste credentials.
2. Only after SMTP delivery is proven, enable the owner-managed `email_verification_required` setting through the supported owner settings interface, if mandatory email verification is the intended signup policy. Test with a fresh address; changing the toggle does not retroactively email existing accounts.
3. Supply the same required SMTP runtime variables to Server 2's worker/Beat environment through its protected, server-local environment file or secret store. Confirm that the worker container sees the values without displaying them.
4. Keep credentials out of Git. Do not add real values to `.env.example`, Compose files, logs, tickets, or this plan. Keep the documented variable names and safe presence checks.
5. Verify both the direct signup OTP flow and an asynchronous notification email. Confirm that failures leave notification delivery status truthful and observable.

**Verification gate:** real message received; signup OTP accepted; asynchronous email accepted; no credential values appear in logs; worker startup no longer reports missing mail credentials.

### C. One-CPU Celery/Beat workload — measure, then tune

**Problem:** the Beat schedule contains several 10-, 30-, and 60-second jobs. With one worker execution slot, a sustained workload can delay other queues. The reported 8.7-second scheduled-booking dispatch needs measurement in context.

**Plan:**
1. Capture a representative 15–30-minute baseline: per-task run duration, start delay, failures/retries, queue depth trend (not a single snapshot), worker CPU/memory, and Beat CPU/memory.
2. Classify each periodic job by business urgency and maximum acceptable delay. Preserve scheduled-booking dispatch, transport recovery, wallet webhook, and ticket-hold timing until their product latency contracts are confirmed.
3. First remove duplicate or unnecessary work, stagger colliding periodic jobs, and bound/optimize expensive database scans. Adjust intervals only for tasks whose service-level requirement allows it.
4. Do not add a second worker or increase concurrency on the 951 MiB host until memory headroom and sustained measurements support it.

**Verification gate:** queues are stable or draining over repeated samples; critical work meets its latency target; no expired/stale task pileup; memory remains inside container and host limits.

### D. Redis and PostgreSQL credential rotation — operational security

**Problem:** existing Redis and database credentials were exposed in prior conversation content.

**Plan:**
1. Before rotation, verify a recoverable database backup and preserve Redis persistence data. Do not remove Docker volumes.
2. Prepare replacement credentials out of band. Prefer a controlled database role transition if equivalent grants/ownership can be proven; otherwise use a coordinated password rotation with a defined maintenance window.
3. Update every consumer on both servers, including Compose/runtime environment files, before retiring the old credentials. Coordinate Redis authentication changes with web sessions, Celery broker/backend, Beat, and any other Redis clients.
4. Recreate only the affected application containers in a controlled order; verify database connections, Redis authentication, worker ping, queue consumption, and website health.
5. Revoke the old credentials and verify that they no longer authenticate. Never place either secret in Git.

**Verification gate:** both servers use the replacement credentials; old credentials fail; DB data, Redis persistence, sessions, and queued jobs are preserved to the extent supported by the planned maintenance procedure.

### E. Off-server backups — operational plus a small integration change if needed

**Problem:** current application backups are local to Server 1; a host loss could take the backups with it.

**Plan:**
1. Confirm database and files backup artifacts complete and pass their SHA-256 checks.
2. Create a private OCI Object Storage bucket and least-privilege upload identity. Use encryption, restricted access, retention/versioning, and lifecycle rules appropriate to the recovery objective.
3. Add a post-success upload step (or a separate reliable sync job) for database and files backups. Record remote object identity and checksum; never upload live `.env` files.
4. Treat configuration snapshots as sensitive because they contain dynamic `SystemConfig` values; restrict and encrypt them accordingly, or exclude them until their contents are classified.
5. Perform a restore drill into an isolated test database and verify the Alembic revision and critical application data. A successful upload alone is not a restore test.

**Verification gate:** a completed backup exists off-host, checksum matches, retention is active, and a restore has been proven without touching production data.

### F. Isolated ARM staging environment — infrastructure

**Plan:**
1. Provision a separate ARM64 Oracle instance only after checking account quota, capacity, and a realistic memory/disk budget.
2. Use a separate staging network boundary, domain, secrets, PostgreSQL database, and Redis instance. Never point staging at production DB/Redis or use live production credentials.
3. Validate Python 3.13 dependencies and build/test the application image for ARM64 (and amd64 where production still needs it). Add an architecture smoke test to CI.
4. Deploy staging from a pinned commit and exercise migrations, email delivery, Celery/Beat, wallet/transport test flows, backup/restore, and rollback before production releases.

**Verification gate:** staging is isolated, builds and runs on ARM64, and has a repeatable deploy/rollback path.

### G. Server 2 operating-system lifecycle — Q1 2027 target

**Plan:**
1. Keep the currently ESM-covered Ubuntu 20.04 worker stable while code, backup, and staging work proceeds.
2. Use the ARM staging work to validate a clean replacement build. Prefer a fresh instance and controlled cutover over an in-place multi-release OS upgrade on the live worker.
3. Reassess the target image in Q1 2027. As of this plan date, Ubuntu 26.04 LTS is available and has a published standard-support end date of May 2031; Ubuntu 24.04 LTS standard support ends May 2029; Ubuntu 22.04 LTS standard support ends May 2027. Avoid choosing 22.04 as a short-lived intermediate production target without a specific compatibility reason.
4. Keep the old worker instance intact until the new host has passed worker/Beat, network, resource, queue, and rollback checks.

**Verification gate:** new host is patched and supported, the exact production image runs correctly, private DB/Redis access is restricted correctly, and rollback to the old host is documented and tested.

## 3. Execution order

1. **Protect data and prepare security rotation:** verify a recoverable backup, then schedule coordinated Redis and DB credential rotation.
2. **Implement and test Celery context/result correctness** in a focused code change; do not include unrelated feature work.
3. **Prove SMTP from Server 1, configure Server 2 runtime mail variables, and verify both signup and async email.**
4. **Measure and tune scheduler load** using actual duration and queue-lag evidence, preserving business latency contracts.
5. **Implement and prove off-host backup replication and restore.**
6. **Build isolated ARM64 staging** and use it for the later OS replacement rehearsal.
7. **Replace Server 2's OS in Q1 2027**, retaining the old host until cutover is proven.

## 4. Change boundaries

- Code changes belong in focused commits with tests; release images are built from a tested commit.
- Secrets and runtime `.env.docker` values never belong in Git.
- Server-local `docker-compose.worker.yml` and other intentionally untracked files must be preserved and reviewed before any edit.
- No production DB writes, migrations, Redis flushes, queue purges, volume deletion, or OS upgrades are part of this planning step.
- Do not rebuild Server 1 for a worker-only fix. Rebuild/recreate only services that contain the changed code.
- A host-level staging or OS change must not be used as a substitute for application-level tests.

## 5. Official Ubuntu lifecycle references

- Ubuntu release cycle: https://ubuntu.com/about/release-cycle
- Ubuntu Expanded Security Maintenance: https://ubuntu.com/security/esm
- Ubuntu 26.04 LTS release notes: https://documentation.ubuntu.com/release-notes/26.04/
