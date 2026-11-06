"""Retired legacy SMTP smoke-test entry point.

The old implementation bypassed the Owner-managed provider and used a
hard-coded recipient with Flask-Mail directly. Use the supported diagnostic
instead:

    python scripts/ops/send_smtp_test_email.py --to <mailbox-you-control>

For the production readiness check, use the Owner page's asynchronous Celery
test so the actual Server 2 worker path is exercised.
"""


def send_mail_test():
    raise SystemExit(
        "This legacy test has been retired. Use "
        "scripts/ops/send_smtp_test_email.py --to <mailbox-you-control>."
    )


if __name__ == "__main__":
    send_mail_test()
