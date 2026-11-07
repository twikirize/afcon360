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
- Record the OCI S3-compatible endpoint and region for the chosen bucket's tenancy/region. For path-style access, the current OCI endpoint format is `https://<namespace>.compat.objectstorage.<region>.oci.customer-oci.com`; use your tenancy's actual Object Storage namespace and region identifier.
- OCI's S3 compatibility API requires Signature Version 4 and path-style requests. AFCON360 configures boto3 accordingly.

### Bucket-scoped IAM permissions

For normal backups up to OCI's 50-GiB `PutObject` limit, the application streams the backup through a single PUT request. A user in a dedicated OCI group can be granted only create/overwrite and read/inspect permissions on the intended bucket and object prefix. Example policy statements (replace the placeholders):

```text
Allow group <backup-group> to manage objects in compartment <backup-compartment> where all {target.bucket.name = '<private-backup-bucket>', target.object.name = 'afcon360/backups/*', any {request.permission = 'OBJECT_CREATE', request.permission = 'OBJECT_OVERWRITE', request.permission = 'OBJECT_READ', request.permission = 'OBJECT_INSPECT'}}
```

For the staging drill, use a separate policy with the object-name prefix `afcon360/oci-backup-drills/*` and the staging bucket name. The policy's `any {request.permission ...}` condition restricts the `manage objects` verb to the four listed object permissions; it does not grant bucket administration or object deletion. Create the policy in the bucket's compartment. The OCI IAM group reference syntax can differ for Identity Domains; use the exact group principal format shown by the OCI policy editor for your domain.

Backups larger than 50 GiB use boto3 multipart upload. Multipart completion needs additional bucket/object permissions; aborting a failed multipart upload needs `OBJECT_DELETE`. Do not silently add broad object-management rights to the normal key. Review that exceptional path separately, scope it to a dedicated bucket/prefix, and configure an OCI Object Lifecycle Management `ABORT` rule for stale incomplete multipart uploads.

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
<BACKUP_OFFSITE_PREFIX>/<environment>/<backup-type>/<year>/<month>/<backup-public-id>/<filename>
```

For example, database and files backups go to separate type prefixes. Each object key includes the unique backup record public ID, preventing same-second backup-name collisions. The database backup record stores the exact object key and checksum. Remote objects are not automatically deleted by local retention cleanup; configure and review OCI lifecycle retention separately.

## GitHub real-OCI recovery drill

PR #35 adds `.github/workflows/oci-backup-recovery-drill.yml`. It uses a GitHub-hosted Ubuntu runner and two disposable PostgreSQL 15 instances; it does not connect to either production server or production database.

Before running it, create the protected GitHub environment named `oci-backup-staging` and configure:

**Environment variables**
- `BACKUP_OFFSITE_BUCKET`: the private staging bucket name.
- `OCI_REGION`: the OCI region identifier.
- `OCI_ENDPOINT_URL`: the namespace-specific S3-compatible HTTPS endpoint.

**Environment secrets**
- `BACKUP_OFFSITE_ACCESS_KEY`: the dedicated OCI Customer Secret Key access key.
- `BACKUP_OFFSITE_SECRET_KEY`: its secret key.

Set environment protection to allow only the trusted backup feature branch while PR #35 is being tested (and `main` after it is merged). Require an authorized reviewer to approve access before the job receives the secrets. Never add these values as repository-wide secrets or commit them to Git.

The workflow:
1. Applies the reviewed Alembic migrations to an empty PostgreSQL 15 source database.
2. Creates one synthetic user and a unique recovery-marker row.
3. Calls the application's actual `BackupService.create_database_backup()` with OCI upload enabled.
4. Confirms that OCI accepted the object and that AFCON360 streamed the object back and validated the full SHA-256 checksum.
5. Starts a separate disposable PostgreSQL 15 container and pre-creates a database named `afcon360_restore_test_...`.
6. Runs `restore_oci_backup_to_test_db.py` to download the object from OCI and restore it into that database.
7. Requires the restored Alembic revision, non-system table count, user count and synthetic marker to match the source.

The test object remains under `afcon360/oci-backup-drills/staging` in the staging bucket. Set a reviewed staging-bucket lifecycle rule to expire drill objects after the agreed retention period; the backup identity does not need permission to delete objects.

The workflow runs on pushes to the PR #35 feature branch. The initial run will stop safely and name any missing environment settings. After creating the environment and adding the settings, rerun the failed job from GitHub Actions. Once merged, the workflow can also be run manually with its explicit confirmation checkbox.

A successful result must show all of `OCI_UPLOAD_VERIFIED=true`, `OCI_REMOTE_READBACK_VERIFIED=true`, `OCI_DOWNLOAD_VERIFIED=true`, `POSTGRES_RESTORE_VERIFIED=true`, and `RESTORED_DATA_MARKER_VERIFIED=true`. A missing-secret/preflight failure is not a recovery result.

## Safe rollout and proof

1. Confirm the backup artifact directory is persistent on the host or a Docker volume. A path inside a container's writable layer can disappear when that container is replaced.
2. Configure a staging bucket and dedicated test identity first.
3. Confirm a local database backup can be created successfully.
4. Enable off-site upload in staging and verify the returned metadata says `verified: true`.
5. Download and verify the exact recorded object with `scripts/ops/restore_oci_backup_to_test_db.py`.
6. Create a **disposable** PostgreSQL database whose name starts with `afcon360_restore_test_`. Supply its connection values via the `BACKUP_RESTORE_TEST_PG*` variables; do not point these at the live production database.
7. Set `BACKUP_OFFSITE_ENVIRONMENT=staging` (or `test`) and `BACKUP_RESTORE_CONFIRMATION=RESTORE_ONLY_TO_DISPOSABLE_TEST_DATABASE`, then run:

   ```powershell
   python scripts/ops/restore_oci_backup_to_test_db.py --object-key "<recorded-object-key>" --sha256 "<recorded-sha256>" --expected-size <recorded-size>
   ```

   The utility downloads the full object, checks byte count and SHA-256, and restores using `psql --single-transaction` into the pre-created test database. It refuses other database names and does not create or drop databases. After restore it reports the Alembic revision, non-system table count and user count. The SQL dump can drop/recreate objects **inside that test database**, so it must be disposable.
8. Verify the reported database name, restored table count and Alembic revision/selected data. Keep the downloaded artifact only if requested with `--keep-download`.
9. Only after the staging upload and restore drill pass should production credentials/settings be added and the feature enabled on the required servers.

A green upload or checksum check is not a restore drill. Production readiness requires both.

## Failure handling

- If upload or remote verification fails, do not treat the backup as off-site protected. The operation is marked failed and logs should identify the failed stage without exposing credentials.
- Keep the local artifact until a verified remote copy and restore test exist.
- Do not flush Redis, remove Docker volumes, delete old backups, or enable a destructive lifecycle policy as part of this setup.
