# AFCON360 production email verification

**Status:** Production delivery is not yet proven. This guide is an operational procedure; it does not contain or change credentials.

## Findings from the current production check

- The production `auth_configurations.email_verification_required` setting was `false`. New email/password registrations therefore did not trigger the signup OTP flow.
- Server 1 previously had SMTP environment values, while Server 2 reported missing `MAIL_USERNAME` and `MAIL_PASSWORD`. Those environment values are now only a migration fallback; their absence on Server 2 is not a delivery test.
- The canonical provider is the encrypted `communication_settings` row with key `email_provider`. Both web and Celery resolve this same PostgreSQL row. Once the row exists, it is authoritative; the environment fallback is not used.
- Normal signup OTP and notification email delivery use the unified `EmailHandler` and the same SMTP transport. The `sendgrid_enabled` database flag or absence of `SENDGRID_API_KEY` does not prove SMTP delivery.

## 1. Configure the Owner-managed SMTP provider

The Owner or Super Admin opens:

`/owner/communication-settings`

Enter the SMTP host, port, username, password/app password, default sender and exactly one TLS mode. The username and password fields are write-only: after saving, the page shows only whether each value is configured. A blank password field preserves the existing password. The explicit **Clear** control removes stored SMTP authentication.

The UI writes one canonical provider record. Its complete JSON configuration is encrypted before it is saved. The root `ENCRYPTION_KEY` is never stored in that same database; it must already exist in the protected runtime environment on both Server 1 and Server 2, and both must use the same existing key.

The deployment environment's `MAIL_*` values are a migration fallback only until the Owner-managed row is created. Once the database row exists, it is authoritative. Do not try to repair Server 2 by copying SMTP credentials into its worker Compose file.

## 2. Test the actual asynchronous worker

Use an address you explicitly control. From the Owner communication settings page, select **Queue email test**. This queues `notifications.send_email_test` through Redis and the real Celery worker. The worker uses the same provider resolver as web requests and normal notification emails.

The page reports the Celery task state and a safe error code. A successful result means the SMTP server accepted the message; it does not prove final mailbox delivery. Check Inbox and Spam/Junk.

A one-off server-side diagnostic is also available from either application container:

```bash
docker exec afcon360_web python scripts/ops/send_smtp_test_email.py --to YOUR_TEST_MAILBOX
```

Expected outcomes:

- `SMTP_TEST_ACCEPTED`: the SMTP provider accepted the message. Check Inbox and Spam/Junk.
- `SMTP_TEST_BLOCKED`: the recipient or provider configuration is invalid/incomplete.
- `SMTP_TEST_FAILED`: delivery failed. Only a safe provider error code or exception class is printed; inspect protected logs without exporting raw environment values.

Do not enable mandatory signup verification until a real message from the asynchronous test arrives at the chosen mailbox.

## 3. Enable verification only after SMTP is proven

Use the AFCON360 owner interface:

`Admin → Owner Settings → Authentication Settings → Email Verification Required`

Enable the setting through that supported interface. Do not update the production database manually.

The change affects new registrations after it is enabled. It does not automatically send a code to an account created earlier while verification was disabled. Use the supported resend-verification flow for an existing account if one is offered.

Then test with a fresh address and complete the six-digit OTP or verification-link flow.

## 3. Correct Server 2 worker mail configuration

The worker currently reports `MAIL_USERNAME` and `MAIL_PASSWORD` missing.

1. On Server 2, inspect the `env_file` entries in the server-local `docker-compose.worker.yml`. Preserve that untracked file; do not replace it with a repository Compose file.
2. Add the same required SMTP runtime settings (host, port, TLS/SSL mode, username, password and default sender) to the protected host-side environment file actually referenced by that Compose file.
3. Do not add credentials to Git, chat, shell output, or screenshots.
4. Recreate only the worker and Beat containers so they receive the new environment. Do not restart PostgreSQL or Redis.
5. Confirm presence without revealing values:

```bash
for C in afcon360_worker afcon360_beat; do
  echo "===== $C ====="
  docker inspect "$C" --format '{{range .Config.Env}}{{println .}}{{end}}' |
  awk -F= '
    $1 ~ /^(MAIL_SERVER|MAIL_PORT|MAIL_USE_TLS|MAIL_USE_SSL|MAIL_USERNAME|MAIL_PASSWORD|MAIL_DEFAULT_SENDER)$/ {
      value=substr($0, index($0, "=")+1)
      print $1 "=" (length(value) ? "SET" : "EMPTY")
      seen[$1]=1
    }
    END {
      split("MAIL_SERVER MAIL_PORT MAIL_USE_TLS MAIL_USE_SSL MAIL_USERNAME MAIL_PASSWORD MAIL_DEFAULT_SENDER", keys, " ")
      for (i in keys) if (!(keys[i] in seen)) print keys[i] "=MISSING"
    }'
done
```

6. Run a real asynchronous notification email test after the worker has the settings. A successful signup OTP from Server 1 alone does not prove Server 2 mail delivery.

## 4. Root/system secret configuration

These values are infrastructure bootstrap secrets, not ordinary communication-provider credentials, and must not be saved in the Owner settings database:

- `SECRET_KEY` — Flask signing/session security.
- `ENCRYPTION_KEY` — decrypts encrypted provider settings and other application data.
- `SECURITY_SALT` and any configured MFA encryption key.
- PostgreSQL and Redis credentials/URLs, including Celery broker and result-backend URLs.
- Payment-provider master credentials and any storage/backup access keys.

Provision or rotate these only through the protected host-side environment/secret mechanism used by the deployment. Apply them consistently to the web and worker containers that need them. Protect host files (for example, owner-only permissions), preserve the current production `ENCRYPTION_KEY`, and never put values in Git, command output, support messages, screenshots or application logs. Changing `ENCRYPTION_KEY` without a separately reviewed re-encryption plan can make existing encrypted records unreadable.

The application log redaction layer removes registered runtime secret values, common credential assignments, authorization headers, URL passwords and nested secret-named structured fields before Python log handlers format records. This is defense in depth, not permission to log credentials. Code must never deliberately log secret values, request bodies containing secrets, or raw provider exceptions. Prefer exception classes and short diagnostic codes.

## 5. Delivery evidence to record

For each test, record only:

- Which process sent it (web diagnostic or Celery worker test).
- Whether SMTP accepted the message.
- Whether it arrived in Inbox or Spam/Junk.
- The safe provider error code or exception class if it failed.
- Whether the relevant notification reached the expected delivered/failed state.

Never record the recipient's OTP, SMTP password, API key, root key, or full environment file in the deployment log.
