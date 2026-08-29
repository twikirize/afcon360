import re

with open(r'C:\Users\OBED\Desktop\afcon360_app\tests\wallet\test_ledger_concurrency.py', 'r') as f:
    content = f.read()

# 1. Add AccountType and AccountStatus to imports
content = content.replace(
    'from app.wallet.models.ledger import AccountModel, LedgerEntryModel, EntryType, AccountOwnerType',
    'from app.wallet.models.ledger import AccountModel, LedgerEntryModel, EntryType, AccountOwnerType, AccountType, AccountStatus'
)

# 2. Fix funded_account fixture
content = content.replace(
    '''@ pytest.fixture
def funded_account(app, test_user):
    """Create a funded account for testing."""
    account = AccountRepository().get_or_create(test_user.id, AccountOwnerType.USER, 'USD')''',
    '''@ pytest.fixture
def funded_account(app, test_user):
    """Create a funded account for testing."""
    from app.wallet.routes import get_or_create_account
    account = get_or_create_account(test_user.id, 'USD')'''
)

# 3. Fix test_user_wallet_ownership
content = content.replace(
    '''    def test_user_wallet_ownership(self, app, test_user):
        """Test that a user can own a wallet."""
        account = AccountRepository().get_or_create(test_user.id, AccountOwnerType.USER, 'USD')''',
    '''    def test_user_wallet_ownership(self, app, test_user):
        """Test that a user can own a wallet."""
        from app.wallet.routes import get_or_create_account
        account = get_or_create_account(test_user.id, 'USD')'''
)

# 4. Fix test_organisation_wallet_ownership
content = content.replace(
    '''    def test_organisation_wallet_ownership(self, app):
        """Test that an organisation can own a wallet."""
        from app.identity.models.organisation import Organisation
        
        org = Organisation(
            org_id=str(uuid4()),
            legal_name="Test Organisation",''',
    '''    def test_organisation_wallet_ownership(self, app):
        """Test that an organisation can own a wallet."""
        from app.identity.models.organisation import Organisation
        
        org = Organisation(
            org_id=str(uuid4()),
            legal_name="Test Organisation " + str(uuid4()),'''
)

# 5. Fix the get_or_create call in test_organisation_wallet_ownership
content = content.replace(
    '''        account = AccountRepository().get_or_create(org.id, AccountOwnerType.ORGANISATION, 'UGX')''',
    '''        from app.wallet.routes import get_or_create_account
        account = get_or_create_account(org.id, 'UGX')'''
)

# 6. Fix test_user_and_org_wallets_separate
content = content.replace(
    '''    def test_user_and_org_wallets_separate(self, app, test_user):
        """Test that user wallet and org wallet are separate."""
        from app.identity.models.organisation import Organisation
        
        org = Organisation(
            org_id=str(uuid4()),
            legal_name="Test Org",''',
    '''    def test_user_and_org_wallets_separate(self, app, test_user):
        """Test that user wallet and org wallet are separate."""
        from app.identity.models.organisation import Organisation
        
        org = Organisation(
            org_id=str(uuid4()),
            legal_name="Test Org " + str(uuid4()),'''
)

# 7. Fix user_account creation in test_user_and_org_wallets_separate
content = content.replace(
    '''        user_account = AccountRepository().get_or_create(test_user.id, AccountOwnerType.USER, 'USD')''',
    '''        from app.wallet.routes import get_or_create_account
        user_account = get_or_create_account(test_user.id, 'USD')'''
)

# 8. Fix org_account creation in test_user_and_org_wallets_separate
content = content.replace(
    '''        org_account = AccountRepository().get_or_create(org.id, AccountOwnerType.ORGANISATION, 'UGX')''',
    '''        from app.wallet.routes import get_or_create_account
        org_account = get_or_create_account(org.id, 'UGX')'''
)

# Fix funded_account fixture
content = content.replace(
    '''@ pytest.fixture
def funded_account(app, test_user):
    """Create a funded account for testing."""
    account = AccountRepository().get_or_create(test_user.id, AccountOwnerType.USER, 'USD')''',
    '''@ pytest.fixture
def funded_account(app, test_user):
    """Create a funded account for testing."""
    from app.wallet.routes import get_or_create_account
    account = get_or_create_account(test_user.id, 'USD')'''
)

# Fix recipient_account in transfer test (first occurrence)
content = content.replace(
    "recipient_account = AccountRepository().get_or_create(recipient.id, AccountOwnerType.USER, 'USD')",
    "from app.wallet.routes import get_or_create_account\n            recipient_account = get_or_create_account(recipient.id, 'USD')"
)

# Fix second recipient_account occurrence (in another test)
content = content.replace(
    "recipient_account = AccountRepository().get_or_create(recipient.id, AccountOwnerType.USER, 'USD')\n            recipient_balance_before = LedgerRepository",
    "from app.wallet.routes import get_or_create_account\n            recipient_account = get_or_create_account(recipient.id, 'USD')\n            recipient_balance_before = LedgerRepository"
)

# Fix organisation legal name duplicates
content = content.replace('legal_name="Test Organisation",', 'legal_name="Test Organisation " + str(uuid4()),')
content = content.replace('legal_name="Test Org",', 'legal_name="Test Org " + str(uuid4()),')

with open(r'C:\Users\OBED\Desktop\afcon360_app\tests\wallet\test_ledger_concurrency.py', 'w') as f:
    f.write(content)

print('All fixes applied')