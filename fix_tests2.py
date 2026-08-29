with open(r'C:\Users\OBED\Desktop\afcon360_app\tests\wallet\test_ledger_concurrency.py', 'r') as f:
    content = f.read()

# Fix test_user_wallet_ownership
old1 = '''    def test_user_wallet_ownership(self, app, test_user):
        """Test that a user can own a wallet."""
        account = AccountRepository().get_or_create(test_user.id, AccountOwnerType.USER, 'USD')'''
new1 = '''    def test_user_wallet_ownership(self, app, test_user):
        """Test that a user can own a wallet."""
        from app.wallet.routes import get_or_create_account
        account = get_or_create_account(test_user.id, 'USD')'''
content = content.replace(old1, new1)

# Fix organisation test - unique legal name
content = content.replace(
    'legal_name="Test Organisation",',
    'legal_name="Test Organisation " + str(uuid4()),'
)

# Fix test_user_and_org_wallets_separate - unique legal name
content = content.replace(
    'legal_name="Test Org",',
    'legal_name="Test Org " + str(uuid4()),'
)

with open(r'C:\Users\OBED\Desktop\afcon360_app\tests\wallet\test_ledger_concurrency.py', 'w') as f:
    f.write(content)

print('Direct fixes applied')