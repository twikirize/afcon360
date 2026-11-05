# OCI off-site backup setup

**Status:** Code support is staged; production upload is not enabled. This guide contains no credentials and does not authorize changing production runtime files.

## What the application does

When `BACKUP_OFFSITE_ENABLED=true`, a successfully created **database** or **files** backup is uploaded to the configured OCI Object Storage bucket. The application then:

1. Checks that the remote object size matches the local artifact.
2. Checks the SHA-256 metadata recorded at upload.
3. Streams the stored object back and recomputes SHA-256 against the local artifact.
4. Records the bucket, object key, checksum, verification time and object version (when provided) in the existing backup record's metadata.

The local backup is retained. If upload or verification fails, the backup operation is recorded as failed, while the local artifact path and checksum remain attached to the record so the failure is visible and can be investigated.

**Configuration snapshots are not uploaded.** They may contain sensitive dynamic system settings and must be classified before inclusion.

## OCI prerequisites

Before enabling the feature:

- Create a dedicated **private** Object Storage bucket for backups. Do not make it public and do not reuse the public media bucket.
- Create a dedicated OCI identity/customer secret key for the backup integration. Grant only the minimum Object Storage permissions needed to create and read objects in this bucket. Do not reuse the media-storage key.
- Decide the bucket's retention/lifecycle policy and any recovery-point requirements. Do not apply automatic deletion until retention and restore requirements are agreed.
- Record the OCI S3-compatible endpoint and region for the chosen bucket's tenancy/region.

## Protected runtime settings

Set these only in the protected server-side runtime environment file (for example, `.env.docker`), never in Git or chat:

```dotenv
BACKUP_OFFSITE_ENABLED=true
BACKUP_OFFSITE_BUCKET=<private-backup-bucket-name>
BACKUP_OFFSITE_ACCESS_KEY=<dedicated-access-key>
BACKUP_OFFSITE_SECRET_KEY=<dedicated-secret-key>
BACKUP_OFFSITE_PREFIX=afcon360/backups
BACKUP_OFFSITE_ENVIRONMENT=production
OCI_REGION=<bucket-region>
OCI_ENDPOINT_URL=<OCI-S3-compatible-endpoint>
```

The same settings must be present in any application process that can initiate a backup. In this deployment, check both the Server 1 web container (manual owner-triggered backups) and Server 2 worker container (scheduled Celery backups). The setting remains disabled unless explicitly enabled.

Do not print the values when checking configuration. Report only `SET`, `EMPTY`, or `MISSING`.

## Object layout

Objects are written under:

```text
<BACKUP_OFFSITE_PREFIX>/<environment>/<backup-type>/<year>/<month>/<filename>
```

For example, database and files backups go to separate type prefixes. The database backup record stores the exact object key and checksum. Remote objects are not automatically deleted by the local retention cleanup; configure and review OCI lifecycle retention separately.

## Safe rollout and proof

1. Confirm the backup artifact directory is persistent on the host or a Docker volume. A path inside a container's writable layer can disappear when that container is replaced.
2. Configure a staging bucket and dedicated test identity first.
3. Confirm a local database backup can be created successfully.
4. Enable off-site upload in staging and verify the returned metadata says `verified: true`.
5. Download the exact recorded object to an isolated restore workspace and run the checksum check again.
6. Restore into a disposable PostgreSQL database, never into `afcon360_prod`, and verify its schema revision and selected data.
7. Only after the staging upload and restore drill pass should production credentials/settings be added and the feature enabled on the required servers.

A green upload or checksum check is not a restore drill. Production readiness requires both.

## Failure handling

- If upload or remote verification fails, do not treat the backup as off-site protected. The operation is marked failed and logs should identify the failed stage without exposing credentials.
- Keep the local artifact until a verified remote copy and restore test exist.
- Do not flush Redis, remove Docker volumes, delete old backups, or enable a destructive lifecycle policy as part of this setup.
