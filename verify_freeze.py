
from app import create_app
from app.extensions import db
from app.wallet.services.wallet_service import WalletService
from app.wallet.repositories.account_repository import AccountRepository
from app.wallet.models.ledger import AccountModel
from app.identity.models.user import User
import uuid
from decimal import Decimal

app = create_app()
with app.app_context():
    # 1. Setup
    email = f'test_freeze_{uuid.uuid4().hex}@example.com'
    user = User(email=email, username=f'test_freeze_{uuid.uuid4().hex}', password_hash='hash')
    db.session.add(user)
    db.session.commit()
    
    account = AccountModel(user_id=user.id, currency='USD')
    db.session.add(account)
    db.session.commit()
    account_id = account.id
    db.session.remove()
    
    # 2. Freeze
    repo = AccountRepository()
    repo.freeze_account(account_id, reason="test freeze")
    db.session.commit()
    print("SUCCESS: Account frozen.")
    
    # 3. Test Block
    service = WalletService()
    try:
        service.deposit(
            account_id=str(account_id),
            amount=Decimal('100.00'),
            currency='USD',
            client_request_id=f"test_freeze_{uuid.uuid4().hex}"
        )
        print("FAILED: Deposit succeeded despite freeze.")
    except Exception as e:
        print(f"SUCCESS: Deposit blocked as expected: {e}")
