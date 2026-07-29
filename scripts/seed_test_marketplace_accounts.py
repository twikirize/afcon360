import os
import sys
from decimal import Decimal

app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, app_dir)

os.environ.setdefault("APP_ENV", "local")

from app import create_app
from app.extensions import db
from app.identity.models.user import User
from app.wallet.routes import get_or_create_account
from app.wallet.services.wallet_service import WalletService

app = create_app()


def seed_test_wallets(
    guest_email: str = "test.guest@afcon360.test",
    host_email: str = "test.host@afcon360.test",
    currency: str = "UGX",
    top_up: Decimal = Decimal("500000.00"),
):
    with app.app_context():
        guest = User.query.filter_by(email=guest_email).first()
        host = User.query.filter_by(email=host_email).first()
        if not guest or not host:
            raise ValueError(
                "Both test users must already exist — create them first if they don't."
            )

        guest_account = get_or_create_account(guest.id, currency)
        host_account = get_or_create_account(host.id, currency)

        wallet = WalletService()
        if guest_account.balance < top_up:
            wallet.deposit(
                account_id=str(guest_account.id),
                amount=top_up - guest_account.balance,
                currency=currency,
                client_request_id=f"seed_topup_{guest.id}",
                metadata={"test_mode": True},
                payment_provider="seed_script",
            )

        print(f"Guest account balance: {guest_account.balance} {currency}")
        print(f"Host account balance: {host_account.balance} {currency}")
        return guest_account, host_account


if __name__ == "__main__":
    seed_test_wallets()