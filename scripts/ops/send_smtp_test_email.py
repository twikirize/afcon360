"""Send one explicit diagnostic email through AFCON360's shared mail transport.

Usage from a running application container:
    python scripts/ops/send_smtp_test_email.py --to test@example.com

The same encrypted Owner-managed provider row is used by web and Celery.
The script sends one generic email and never prints credentials or raw provider errors.
"""
from __future__ import annotations

import argparse
import sys

from app import create_app


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--to",
        required=True,
        help="Mailbox that has explicitly been selected to receive this test",
    )
    args = parser.parse_args()

    from app.utils.security import validate_email

    recipient = (args.to or "").strip()
    if not validate_email(recipient):
        print("SMTP_TEST_BLOCKED: provide a valid recipient address.", file=sys.stderr)
        return 2

    app = create_app()
    with app.app_context():
        from app.notifications.email_transport import (
            EmailDeliveryError,
            send_smtp_email,
        )

        try:
            provider = send_smtp_email(
                recipient=recipient,
                subject="AFCON360 SMTP delivery test",
                body=(
                    "This is a diagnostic email sent from AFCON360 using the "
                    "shared Owner-managed email configuration. It contains no "
                    "verification code or account link. You can ignore this message."
                ),
            )
        except EmailDeliveryError as exc:
            print(
                "SMTP_TEST_FAILED: provider delivery failed (" + exc.code + ")",
                file=sys.stderr,
            )
            return 1
        except Exception as exc:
            print(
                "SMTP_TEST_FAILED: transport raised " + type(exc).__name__,
                file=sys.stderr,
            )
            return 1

    print(
        "SMTP_TEST_ACCEPTED: " + provider
        + " accepted the message. Check the recipient inbox and spam folder."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
