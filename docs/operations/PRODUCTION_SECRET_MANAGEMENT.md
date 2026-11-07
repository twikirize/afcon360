# AFCON360 system secret management

This guide separates **application root secrets** from ordinary provider credentials.

## Root secrets belong in protected runtime configuration

The following values are required to start or securely connect deployed AFCON360 services. Keep them in the protected host-side environment/secret mechanism consumed by Docker Compose:

| Variable / value | Purpose | Handling |
|---|---|---|
| `SECRET_KEY` | Flask signing and session security | Stable, private, same across web instances that share sessions |
| `ENCRYPTION_KEY` | Encrypts/decrypts application secrets stored in PostgreSQL | Stable, private, identical on every web, worker and maintenance process that reads encrypted rows |
| `SECURITY_SALT` | Security-sensitive hashing/derivation | Stable, private |
| MFA encryption key (where configured) | Protects MFA secret material | Stable, private; follow MFA-specific rotation plan |
| PostgreSQL credentials / `DATABASE_URL` | Database access | Server-side secret only |
| Redis credentials / `REDIS_URL` | Session, cache, queue and realtime access | Server-side secret only |
| `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` | Celery transport and result store | Server-side secret only; may contain Redis credentials |
| Payment, backup and external-service API keys | Third-party access | Protected runtime secret or an encrypted provider credential record designed for that integration |

**Do not put root secrets in the Owner communication-settings form or in ordinary database configuration.** In particular, a database cannot safely be the only place that stores the key required to decrypt its own credentials.

The provider-settings service also rejects root application keys, database/Redis connection credentials and Celery broker/backend URLs, including nested fields. These values must be provisioned through the protected runtime environment; encrypting them in the provider table is not an acceptable substitute.

## Shared SMTP provider

The SMTP username, password/app password, host, port, sender and TLS mode are ordinary provider credentials. The Owner/Super Admin configures them at:

`/owner/communication-settings`

They are stored in the `communication_settings` PostgreSQL row under key `email_provider`, as a versioned authenticated-encryption envelope. The web application and Celery worker resolve this same record. A blank password field preserves the stored password; the explicit clear-auth option removes username/password.

The legacy Authentication Settings page also uses an encrypted `auth_providers` settings record for Google OAuth, SendGrid, Twilio and Africa's Talking credentials. That form is write-only: existing values are never rendered back into HTML, blank inputs preserve them, and explicit clear controls remove them. On the first save after this change, existing legacy values are copied into the encrypted record and the former plaintext columns are cleared. Until that first save, existing legacy columns remain a read-only compatibility fallback; the form does not disclose their values.

The existing environment `MAIL_*` values are a migration fallback only when the Owner-managed provider row does not yet exist. Once the row exists, it is authoritative, including when disabled. Do not copy the SMTP password separately into Server 2's worker Compose file.

Before first use, confirm the same already-existing `ENCRYPTION_KEY` is available to both Server 1 and Server 2. Never generate a new key as a quick fix, and never rotate it during ordinary SMTP changes. Key rotation requires a separately reviewed re-encryption and restore plan.

## Provisioning and access procedure

1. Use the supported protected host-side environment file/secret store used by the deployment. Do not commit the file.
2. Restrict file access to the deployment administrator (for a file-based secret source, normally owner read/write only).
3. Pass the required values to every container that needs them using Compose's existing environment mechanism.
4. Do not run commands that print full environment values. Verify presence using a script that prints only `SET`, `EMPTY` or `MISSING`.
5. Recreate only the affected application containers after a reviewed change. Do not restart or remove PostgreSQL/Redis volumes as part of secret configuration.
6. Record only the secret name, change ticket/reference, timestamp, affected services and verification result. Never record the value.

## Logging requirements

Application code must not deliberately log credentials, tokens, authorization headers, private keys, full connection strings or raw provider exceptions. Use a safe error code or exception class instead.

The logging layer installs a LogRecord factory before application handlers format messages. It redacts registered runtime secret values, credential-like assignments, Bearer/Basic authorization values, URL passwords and nested secret-named structured fields. This is defense in depth. It does not sanitize shell `echo`, `print`, reverse-proxy logs, third-party processes outside Python logging, or copies already exported elsewhere. Never use logs as a secret store or paste raw logs containing environment values.

If a secret is found in a log, stop further exposure, restrict access to the affected log artifact and follow the incident/credential-rotation procedure for that specific secret. Do not rotate `ENCRYPTION_KEY` without the planned re-encryption process.