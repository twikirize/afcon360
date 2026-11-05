# AFCON360 production email verification

**Status:** Production delivery is not yet proven. This guide is an operational procedure; it does not contain or change credentials.

## Findings from the current production check

- The production `auth_configurations.email_verification_required` setting was `false`. New email/password registrations therefore did not trigger the signup OTP flow.
- Server 1's web container had SMTP server, username, password, port, TLS/SSL flags and default sender present.
- Server 2's worker logs reported `MAIL_USERNAME` and `MAIL_PASSWORD` missing. Asynchronous email delivery from that worker cannot be relied on until its runtime environment is corrected.
- The current signup OTP path calls `OTPService.send_email_otp_checked`, which calls the Flask-Mail `EmailHandler`. That handler uses the configured SMTP transport. The `sendgrid_enabled` database flag or absence of `SENDGRID_API_KEY` does not prove the SMTP path is working or broken.

## 1. Prove SMTP from Server 1 first

Use an address you explicitly choose for the test. Do not use a guessed or inferred recipient.

From Server 1, run inside the web container:

```bash
docker exec afcon360_web python scripts/ops/send_smtp_test_email.py --to YOUR_TEST_MAILBOX
```

Expected outcomes:

- `SMTP_TEST_ACCEPTED`: the SMTP transport accepted the message. This does not prove inbox delivery; check Inbox and Spam/Junk.
- `SMTP_TEST_BLOCKED`: one or more required settings are absent or contradictory.
- `SMTP_TEST_FAILED`: mail transport raised an exception. The script prints only the exception class; inspect protected Server 1 logs for the detailed provider error. Never paste credentials or raw environment files.

Do not enable mandatory signup verification until the test message arrives at the chosen mailbox.

## 2. Enable verification only after SMTP is proven

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

## 4. Delivery evidence to record

For each test, record only:

- Which server/container sent it.
- Whether SMTP accepted the message.
- Whether it arrived in Inbox or Spam/Junk.
- The provider error class if it failed.
- Whether the relevant notification record reached the expected delivered/failed state.

Never record the recipient's OTP, SMTP password, API key, or full environment file in the deployment log.
