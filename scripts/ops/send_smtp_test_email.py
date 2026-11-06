"""Send one explicit diagnostic email through AFCON360's configured Flask-Mail transport.

Usage from a running application container:
    python scripts/ops/send_smtp_test_email.py --to test@example.com

This sends a generic diagnostic message only. It never prints mail credentials.
"""

from __future__ import annotations

import argparse
import sys

from app import create_app
from app.extensions import mail


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--to",
        required=True,
        help="Mailbox that has explicitly been selected to receive this test",
    )
    args = parser.parse_args()

    recipient = (args.to or "").strip()
    if not recipient or "@" not in recipient or recipient.startswith("@") or recipient.endswith("@"):
        print("SMTP_TEST_BLOCKED: provide a valid recipient address.", file=sys.stderr)
        return 2

    app = create_app()
    with app.app_context():
        required = (
            "MAIL_SERVER",
            "MAIL_PORT",
            "MAIL_USERNAME",
            "MAIL_PASSWORD",
            "MAIL_DEFAULT_SENDER",
        )
        missing = [
            name for name in required
            if not app.config.get(name)
        ]
        if missing:
            print(
                "SMTP_TEST_BLOCKED: missing runtime settings: "
                + ", ".join(missing),
                file=sys.stderr,
            )
            return 2

        if app.config.get("MAIL_USE_TLS") and app.config.get("MAIL_USE_SSL"):
            print(
                "SMTP_TEST_BLOCKED: MAIL_USE_TLS and MAIL_USE_SSL cannot both be enabled.",
                file=sys.stderr,
            )
            return 2

        from flask_mail import Message

        message = Message(
            subject="AFCON360 SMTP delivery test",
            recipients=[recipient],
            body=(
                "This is a diagnostic email sent from the AFCON360 production "
                "mail configuration. It contains no verification code or "
                "account link. You can ignore this message."
            ),
        )

        try:
            mail.send(message)
        except Exception as exc:
            # Exception text can contain transport details. Log only its class;
            # inspect protected server logs if more detail is required.
            print(
                "SMTP_TEST_FAILED: mail transport raised "
                + type(exc).__name__,
                file=sys.stderr,
            )
            return 1

    print("SMTP_TEST_ACCEPTED: the configured mail transport accepted the message.")
    print("Check the recipient inbox and spam folder to confirm final delivery.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
