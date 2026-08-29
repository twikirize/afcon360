import re

with open(r'C:\Users\OBED\Desktop\afcon360_app\tests\wallet\test_ledger_concurrency.py', 'r') as f:
    content = f.read()

# Fix 1: Fix funded_account fixture - replace AccountRepository().get_or_create with get_or_create_account
# The fixture is at module level, so import should be at module level
# Find the fixture and replace the call
content = re.sub(
    r'(@pytest\.fixture\s+def funded_account\(app, test_user\):\s+"""Create a funded account for testing.""")\s+account = AccountRepository\(\).get_or_create\(test_user\.id, AccountOwnerType\.USER, \'USD\'\)',
    r'\1\n    from app.wallet.routes import get_or_create_account\n    account = get_or_create_account(test_user.id, \'USD\')',
    content,
    flags=re.DOTALL
)

# Fix 2: Fix test_user_wallet_ownership
content = re.sub(
    r'(def test_user_wallet_ownership\(self, app, test_user\):\s+"""Test that a user can own a wallet.""")\s+account = AccountRepository\(\).get_or_create\(test_user\.id, AccountOwnerType\.USER, \'USD\'\)',
    r'\1\n        from app.wallet.routes import get_or_create_account\n        account = get_or_create_account(test_user.id, \'USD\')',
    content,
    flags=re.DOTALL
)

# Fix 3: Fix test_organisation_wallet_ownership - replace the get_or_create call
content = re.sub(
    r'(account = AccountRepository\(\).get_or_create\(org\.id, AccountOwnerType\.ORGANISATION, \'UGX\'\))',
    r'from app.wallet.routes import get_or_create_account\n        account = get_or_create_account(org.id, \'UGX\')',
    content
)

# Fix 4: Fix test_user_and_org_wallets_separate - user_account
content = re.sub(
    r'(user_account = AccountRepository\(\).get_or_create\(test_user\.id, AccountOwnerType\.USER, \'USD\'\))',
    r'from app.wallet.routes import get_or_create_account\n        user_account = get_or_create_account(test_user.id, \'USD\')',
    content
)

# Fix 5: Fix test_user_and_org_wallets_separate - org_account
content = re.sub(
    r'(org_account = AccountRepository\(\).get_or_create\(org\.id, AccountOwnerType\.ORGANISATION, \'UGX\'\))',
    r'from app.wallet.routes import get_or_create_account\n        org_account = get_or_create_account(org.id, \'UGX\')',
    content
)

# Fix 6: Fix recipient_account in transfer test
content = re.sub(
    r'(recipient_account = AccountRepository\(\).get_or_create\(recipient\.id, AccountOwnerType\.USER, \'USD\'\))',
    r'from app.wallet.routes import get_or_create_account\n            recipient_account = get_or_create_account(recipient.id, \'USD\')',
    content
)

# Fix 6b: Another recipient_account occurrence
content = re.sub(
    r'(recipient_account = AccountRepository\(\).get_or_create\(recipient\.id, AccountOwnerType\.USER, \'USD\'\)\n\s+recipient_balance_before = LedgerRepository)',
    r'from app.wallet.routes import get_or_create_account\n            recipient_account = get_or_create_account(recipient.id, \'USD\')\n            recipient_balance_before = LedgerRepository',
    content
)

# Fix organisation legal name duplicates
content = content.replace('legal_name="Test Organisation",', 'legal_name="Test Organisation " + str(uuid4()),')
content = content.replace('legal_name="Test Org",', 'legal_name="Test Org " + str(uuid4()),')

with open(r'C:\Users\OBED\Desktop\afcon360_app\tests\wallet\test_ledger_concurrency.py', 'w') as f:
    f.write(content)

print('All regex fixes applied')