with open(r'C:\Users\OBED\Desktop\afcon360_app\tests\wallet\test_ledger_concurrency.py', 'r') as f:
    content = f.read()

# Fix all AccountRepository().get_or_create calls with AccountOwnerType
# Replace with get_or_create_account from wallet.routes

# 1. Fix funded_account fixture
content = content.replace(
    "account = AccountRepository().get_or_create(test_user.id, AccountOwnerType.USER, 'USD')\n",
    "from app.wallet.routes import get_or_create_account\n    account = get_or_create_account(test_user.id, 'USD')\n"
)

# 2. Fix test_user_wallet_ownership
content = content.replace(
    "account = AccountRepository().get_or_create(test_user.id, AccountOwnerType.USER, 'USD')\n",
    "from app.wallet.routes import get_or_create_account\n    account = get_or_create_account(test_user.id, 'USD')\n"
)

# 3. Fix organisation test
content = content.replace(
    "account = AccountRepository().get_or_create(org.id, AccountOwnerType.ORGANISATION, 'UGX')\n",
    "from app.wallet.routes import get_or_create_account\n    account = get_or_create_account(org.id, 'UGX')\n"
)

# 4. Fix recipient in transfer test
content = content.replace(
    "recipient_account = AccountRepository().get_or_create(recipient.id, AccountOwnerType.USER, 'USD')\n",
    "from app.wallet.routes import get_or_create_account\n    recipient_account = get_or_create_account(recipient.id, 'USD')\n"
)

# 5. Fix test_user_and_org_wallets_separate - user_account
content = content.replace(
    "user_account = AccountRepository().get_or_create(test_user.id, AccountOwnerType.USER, 'USD')\n",
    "from app.wallet.routes import get_or_create_account\n    user_account = get_or_create_account(test_user.id, 'USD')\n"
)

# 6. Fix test_user_and_org_wallets_separate - org_account
content = content.replace(
    "org_account = AccountRepository().get_or_create(org.id, AccountOwnerType.ORGANISATION, 'UGX')\n",
    "from app.wallet.routes import get_or_create_account\n    org_account = get_or_create_account(org.id, 'UGX')\n"
)

# Fix organisation legal name duplicates
content = content.replace('legal_name="Test Organisation",', 'legal_name="Test Organisation " + str(uuid4()),')
content = content.replace('legal_name="Test Org",', 'legal_name="Test Org " + str(uuid4()),')

with open(r'C:\Users\OBED\Desktop\afcon360_app\tests\wallet\test_ledger_concurrency.py', 'w') as f:
    f.write(content)

print('All fixes applied')