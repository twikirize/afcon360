
from app import create_app
from app.extensions import db
from app.wallet.services.wallet_service import WalletService
from app.wallet.services.regulatory_reporting import RegulatoryReportingService
from app.wallet.models.ledger import AccountModel
from app.identity.models.user import User
import uuid
from decimal import Decimal

app = create_app()
with app.app_context():
    # 1. Create User and Account
    email = f'test_reg_{uuid.uuid4().hex}@example.com'
    user = User(email=email, username=f'test_reg_{uuid.uuid4().hex}', password_hash='hash')
    db.session.add(user)
    db.session.commit()
    
    account = AccountModel(user_id=user.id, currency='USD')
    db.session.add(account)
    db.session.commit()
    account_id = str(account.id)
    db.session.remove()
    db.session.close()
    
    # 2. Perform Deposits
    service = WalletService()
    for i in range(3):
        service.deposit(
            account_id=account_id,
            amount=Decimal('9500.00'),
            currency='USD',
            client_request_id=f"test_reg_{i}_{uuid.uuid4().hex}"
        )
    print("SUCCESS: Deposits performed.")
        
    # 3. Generate STR Report (Structuring)
    report = RegulatoryReportingService.generate_str_report()
    
    # 4. Verify
    found = False
    for tx in report.suspicious_transactions:
        # RegulatoryReportingService returns dicts
        if tx['pattern'] == 'structuring':
            found = True
            print(f"SUCCESS: Transaction found in STR report: {tx}")
    
    if not found:
        print("FAILED: Transaction not found in STR report.")
