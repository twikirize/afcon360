
Install the latest PowerShell for new features and improvements! https://aka.ms/PSWindows

(.venv) PS C:\Users\ADMIN\Desktop\afcon360_app> # Create a simulation script to demonstrate identity separation
(.venv) PS C:\Users\ADMIN\Desktop\afcon360_app> @"
>> # -*- coding: utf-8 -*-
>> """
>> Identity Separation Simulation - Follows Obed through the system
>> Shows how internal vs external IDs work in practice
>> """
>> import uuid
>> import random
>> from datetime import datetime
>> from decimal import Decimal
>> 
>> class IdentityDemo:
>>     """Demonstrate how Obed is seen across different system layers"""
>>     
>>     def __init__(self, name, email, phone):
>>         self.name = name
>>         self.email = email
>>         self.phone = phone
>>
>>         # System generates IDs at registration
>>         self.internal_user_id = random.randint(10000, 99999)  # BIGINT - NEVER exposed
>>         self.external_user_id = str(uuid.uuid4())  # UUID - ALWAYS exposed in APIs
>>         self.created_at = datetime.now()
>>
>>         print("="*80)
>>         print(f"🔐 USER REGISTRATION: {name}")
>>         print("="*80)
>>         print(f"   Name: {name}")
>>         print(f"   Email: {email}")
>>         print(f"   Phone: {phone}")
>>         print(f"\n   🆔 Internal User ID (BIGINT): {self.internal_user_id}")
>>         print(f"      → Purpose: Database joins, foreign keys, performance")
>>         print(f"      → Visibility: ⚠️ NEVER exposed to API, frontend, or logs")
>>         print(f"\n   🌐 External User ID (UUID): {self.external_user_id}")
>>         print(f"      → Purpose: API responses, URLs, sessions, user identification")
>>         print(f"      → Visibility: ✅ Safe to expose everywhere")
>>
>>     def create_wallet_account(self, currency="USD"):
>>         """Create a wallet account for Obed"""
>>         # Account uses its own identity separate from user
>>         self.account_id = str(uuid.uuid4())  # Account UUID - can be exposed
>>         self.currency = currency
>>         self.balance = Decimal("0.00")
>>
>>         print("\n" + "="*80)
>>         print(f"💰 WALLET CREATION for {self.name}")
>>         print("="*80)
>>         print(f"   Account ID (UUID): {self.account_id}")
>>         print(f"   Currency: {currency}")
>>         print(f"   Initial Balance: ${self.balance}")
>>         print(f"\n   🔗 Relationship (Foreign Key):")
>>         print(f"      account.user_id = {self.internal_user_id} (FK to User.id)")
>>         print(f"      → This links the account to Obed internally")
>>         print(f"      → This BIGINT is NEVER exposed in responses")
>>         return self.account_id
>>
>>     def create_transaction(self, amount, transaction_type="deposit"):
>>         """Create a transaction for Obed"""
>>         transaction_id = str(uuid.uuid4())
>>
>>         # Transaction links to BOTH User and Account
>>         print("\n" + "="*80)
>>         print(f"💸 TRANSACTION: {transaction_type.upper()} for {self.name}")
>>         print("="*80)
>>         print(f"   Transaction ID (UUID): {transaction_id}")
>>         print(f"   Amount: ${amount}")
>>         print(f"   Type: {transaction_type}")
>>         print(f"\n   🔗 Relationships (Foreign Keys):")
>>         print(f"      transaction.user_id = {self.internal_user_id} (FK to User.id)")
>>         print(f"      transaction.account_id = {self.account_id} (FK to Account.id)")
>>
>>         # Update balance
>>         if transaction_type == "deposit":
>>             self.balance += Decimal(str(amount))
>>         elif transaction_type == "withdrawal":
>>             self.balance -= Decimal(str(amount))
>>
>>         print(f"\n   New Balance: ${self.balance}")
>>         return transaction_id
>>
>>     def show_api_response(self):
>>         """Show what an API would return for Obed"""
>>         print("\n" + "="*80)
>>         print(f"📡 API RESPONSE for {self.name}")
>>         print("="*80)
>>         print("✅ CORRECT RESPONSE (what you SHOULD expose):")
>>         print("{")
>>         print(f'    "status": "success",')
>>         print(f'    "data": {{')
>>         print(f'        "user": {{')
>>         print(f'            "user_id": "{self.external_user_id}",        # ✅ UUID (public)')
>>         print(f'            "name": "{self.name}",')
>>         print(f'            "email": "{self.email}"')
>>         print(f'        }},')
>>         print(f'        "wallet": {{')
>>         print(f'            "account_id": "{self.account_id}",          # ✅ UUID (account identifier)')
>>         print(f'            "balance": "{self.balance}",')
>>         print(f'            "currency": "{self.currency}"')
>>         print(f'        }},')
>>         print(f'        "transaction": {{')
>>         print(f'            "transaction_id": "some-uuid-here",        # ✅ UUID')
>>         print(f'            "amount": "100.00"')
>>         print(f'        }}')
>>         print(f'    }}')
>>         print("}")
>>
>>         print("\n❌ WRONG RESPONSE (what you should NEVER expose):")
>>         print("{")
>>         print(f'    "user_id": {self.internal_user_id},                 # ❌ Exposing internal BIGINT!')
>>         print(f'    "wallet": {{')
>>         print(f'        "user_id": {self.internal_user_id},            # ❌ Exposing internal BIGINT again!')
>>         print(f'        "balance": "{self.balance}"')
>>         print(f'    }}')
>>         print("}")
>>
>>     def show_database_view(self):
>>         """Show how the database sees Obed"""
>>         print("\n" + "="*80)
>>         print(f"🗄️ DATABASE VIEW for {self.name}")
>>         print("="*80)
>>         print("users table:")
>>         print("┌─────────┬──────────────────────────────────────┬─────────────┐")
>>         print("│ id(BIGINT) │ public_id(UUID)                    │ name        │")
>>         print("├─────────┼──────────────────────────────────────┼─────────────┤")
>>         print(f"│ {self.internal_user_id} │ {self.external_user_id} │ {self.name} │")
>>         print("└─────────┴──────────────────────────────────────┴─────────────┘")
>>
>>         print("\naccounts table:")
>>         print("┌──────────────────────────────────┬───────────┬─────────┐")
>>         print("│ id(UUID)                         │ user_id   │ balance │")
>>         print("├──────────────────────────────────┼───────────┼─────────┤")
>>         print(f"│ {self.account_id} │ {self.internal_user_id} │ ${self.balance} │")
>>         print("└──────────────────────────────────┴───────────┴─────────┘")
>>
>>     def show_logging_view(self):
>>         """Show how logging should work"""
>>         print("\n" + "="*80)
>>         print(f"📝 LOGGING VIEW for {self.name}")
>>         print("="*80)
>>         print("✅ CORRECT LOGGING (use public_id):")
>>         print(f'   logger.info(f"User {self.external_user_id} performed action")')
>>
>>         print("\n❌ WRONG LOGGING (NEVER use internal BIGINT in logs):")
>>         print(f'   logger.info(f"User {self.internal_user_id} performed action")  # SECURITY RISK!')
>>
>>     def run_full_demo(self):
>>         """Run complete demonstration"""
>>         self.create_wallet_account()
>>         self.create_transaction("100.00", "deposit")
>>         self.create_transaction("25.50", "withdrawal")
>>         self.show_api_response()
>>         self.show_database_view()
>>         self.show_logging_view()
>>         
>>         print("\n" + "="*80)
>>         print("📊 SUMMARY: How the System Sees Obed")
>>         print("="*80)
>>         print(f"""
>>     Where is Obed's identity used?
>>     ─────────────────────────────────────────────────────────────────
>>
>>     1. 🔐 LOGIN PAGE:
>>        - Obed enters: email/phone + password
>>        - System looks up by email/phone → returns User object
>>
>>     2. 🆔 AFTER LOGIN (Session):
>>        - Flask-Login stores: user.get_id() = {self.external_user_id}
>>        - Session cookie contains: public_id (UUID)
>>        - NEVER stores the internal BIGINT in session
>>
>>     3. 💰 WALLET API:
>>        - Request: GET /api/wallet/balance
>>        - System gets: current_user.public_id = {self.external_user_id}
>>        - Converts to internal: user = User.get_by_public_id(public_id)
>>        - Uses: user.id = {self.internal_user_id} to query database
>>
>>     4. 🗄️ DATABASE QUERIES:
>>        - SELECT * FROM accounts WHERE user_id = {self.internal_user_id}
>>        - All queries use the BIGINT for performance
>>
>>     5. 📡 API RESPONSE:
>>        - Returns: user_id = {self.external_user_id} (UUID)
>>        - Returns: account_id = {self.account_id} (UUID)
>>        - NEVER returns the internal BIGINT
>>
>>     6. 📝 LOGS:
>>        - Log entries use: public_id = {self.external_user_id}
>>        - Internal BIGINT {self.internal_user_id} NEVER appears in logs
>>
>>     7. 🔗 FOREIGN KEYS:
>>        - accounts.user_id = {self.internal_user_id} (FK to users.id)
>>        - transactions.user_id = {self.internal_user_id} (FK to users.id)
>>        - transactions.account_id = {self.account_id} (FK to accounts.id)
>>
>>     ─────────────────────────────────────────────────────────────────
>>     ✅ All IDs are correctly separated by purpose and visibility!
>>     """)
>>
>> # Run the simulation
>> if __name__ == "__main__":
>>     # Create Obed's account
>>     obed = IdentityDemo(
>>         name="Obed",
>>         email="obed@example.com",
>>         phone="+256700000000"
>>     )
>>     obed.run_full_demo()
>> "@ | Out-File -FilePath identity_demo.py -Encoding utf8
(.venv) PS C:\Users\ADMIN\Desktop\afcon360_app> 
(.venv) PS C:\Users\ADMIN\Desktop\afcon360_app> python identity_demo.py
================================================================================
🔐 USER REGISTRATION: Obed
================================================================================
   Name: Obed
   Email: obed@example.com
   Phone: +256700000000

   🆔 Internal User ID (BIGINT): 92240
      → Purpose: Database joins, foreign keys, performance
      → Visibility: ⚠️ NEVER exposed to API, frontend, or logs

   🌐 External User ID (UUID): 5c0bdc66-4388-45af-b008-d5816c40a4cc
      → Purpose: API responses, URLs, sessions, user identification
      → Visibility: ✅ Safe to expose everywhere

================================================================================
💰 WALLET CREATION for Obed
================================================================================
   Account ID (UUID): 77a85b56-c8f0-4e72-97d1-3d174b595eea
   Currency: USD
   Initial Balance:

   🔗 Relationship (Foreign Key):
      account.user_id = 92240 (FK to User.id)
      → This links the account to Obed internally
      → This BIGINT is NEVER exposed in responses

================================================================================
💸 TRANSACTION: DEPOSIT for Obed
================================================================================
   Transaction ID (UUID): 4149be14-4e82-4731-91c3-68a0a77294b4
   Amount:
   Type: deposit

   🔗 Relationships (Foreign Keys):
      transaction.user_id = 92240 (FK to User.id)
      transaction.account_id = 77a85b56-c8f0-4e72-97d1-3d174b595eea (FK to Account.id)

   New Balance:

================================================================================
💸 TRANSACTION: WITHDRAWAL for Obed
================================================================================
   Transaction ID (UUID): 0eac6804-c4be-4bf1-a285-9fe5e15bb426
   Amount:
   Type: withdrawal

   🔗 Relationships (Foreign Keys):
      transaction.user_id = 92240 (FK to User.id)
      transaction.account_id = 77a85b56-c8f0-4e72-97d1-3d174b595eea (FK to Account.id)

   New Balance:

================================================================================
📡 API RESPONSE for Obed
================================================================================
✅ CORRECT RESPONSE (what you SHOULD expose):
{
    "status": "success",
    "data": {
        "user": {
            "user_id": "5c0bdc66-4388-45af-b008-d5816c40a4cc",        # ✅ UUID (public)
            "name": "Obed",
            "email": "obed@example.com"
        },
        "wallet": {
            "account_id": "77a85b56-c8f0-4e72-97d1-3d174b595eea",          # ✅ UUID (account identifier)
            "balance": "74.50",
            "currency": "USD"
        },
        "transaction": {
            "transaction_id": "some-uuid-here",        # ✅ UUID
            "amount": "100.00"
        }
    }
}

❌ WRONG RESPONSE (what you should NEVER expose):
{
    "user_id": 92240,                 # ❌ Exposing internal BIGINT!
    "wallet": {
        "user_id": 92240,            # ❌ Exposing internal BIGINT again!
        "balance": "74.50"
    }
}

================================================================================
🗄️ DATABASE VIEW for Obed
================================================================================
users table:
┌─────────┬──────────────────────────────────────┬─────────────┐
│ id(BIGINT) │ public_id(UUID)                    │ name        │
├─────────┼──────────────────────────────────────┼─────────────┤
│ 92240 │ 5c0bdc66-4388-45af-b008-d5816c40a4cc │ Obed │
└─────────┴──────────────────────────────────────┴─────────────┘

accounts table:
┌──────────────────────────────────┬───────────┬─────────┐
│ id(UUID)                         │ user_id   │ balance │
├──────────────────────────────────┼───────────┼─────────┤
│ 77a85b56-c8f0-4e72-97d1-3d174b595eea │ 92240 │  │
└──────────────────────────────────┴───────────┴─────────┘

================================================================================
📝 LOGGING VIEW for Obed
================================================================================
✅ CORRECT LOGGING (use public_id):
   logger.info(f"User 5c0bdc66-4388-45af-b008-d5816c40a4cc performed action")

❌ WRONG LOGGING (NEVER use internal BIGINT in logs):
   logger.info(f"User 92240 performed action")  # SECURITY RISK!

================================================================================
📊 SUMMARY: How the System Sees Obed
================================================================================

    Where is Obed's identity used?
    ─────────────────────────────────────────────────────────────────

    1. 🔐 LOGIN PAGE:
       - Obed enters: email/phone + password
       - System looks up by email/phone → returns User object

    2. 🆔 AFTER LOGIN (Session):
       - Flask-Login stores: user.get_id() = 5c0bdc66-4388-45af-b008-d5816c40a4cc
       - Session cookie contains: public_id (UUID)
       - NEVER stores the internal BIGINT in session

    3. 💰 WALLET API:
       - Request: GET /api/wallet/balance
       - System gets: current_user.public_id = 5c0bdc66-4388-45af-b008-d5816c40a4cc
       - Converts to internal: user = User.get_by_public_id(public_id)
       - Uses: user.id = 92240 to query database

    4. 🗄️ DATABASE QUERIES:
       - SELECT * FROM accounts WHERE user_id = 92240
       - All queries use the BIGINT for performance

    5. 📡 API RESPONSE:
       - Returns: user_id = 5c0bdc66-4388-45af-b008-d5816c40a4cc (UUID)
       - Returns: account_id = 77a85b56-c8f0-4e72-97d1-3d174b595eea (UUID)
       - NEVER returns the internal BIGINT

    6. 📝 LOGS:
       - Log entries use: public_id = 5c0bdc66-4388-45af-b008-d5816c40a4cc
       - Internal BIGINT 92240 NEVER appears in logs

    7. 🔗 FOREIGN KEYS:
       - accounts.user_id = 92240 (FK to users.id)
       - transactions.user_id = 92240 (FK to users.id)
       - transactions.account_id = 77a85b56-c8f0-4e72-97d1-3d174b595eea (FK to accounts.id)

    ─────────────────────────────────────────────────────────────────
    ✅ All IDs are correctly separated by purpose and visibility!

(.venv) PS C:\Users\ADMIN\Desktop\afcon360_app> 

Copyright (C) Microsoft Corporation. All rights reserved.

Install the latest PowerShell for new features and improvements! https://aka.ms/PSWindows

(.venv) PS C:\Users\ADMIN\Desktop\afcon360_app> # Direct database diagnostic script
(.venv) PS C:\Users\ADMIN\Desktop\afcon360_app> @"
>> # -*- coding: utf-8 -*-
>> """
>> Direct Database Identity Separation Check
>> Run this directly to see your database schema
>> """
>> import os
>> import sys
>> 
>> # Add project root to path
>> sys.path.insert(0, os.path.abspath('.'))
>> 
>> # Set environment
>> os.environ['FLASK_ENV'] = 'testing'
>> os.environ['SKIP_TEST_DB_CHECK'] = '1'
>>
>> try:
>>     from app import create_app
>>     from app.extensions import db
>>     from sqlalchemy import text, inspect
>>
>>     print("\n" + "="*80)
>>     print(" IDENTITY SEPARATION DATABASE CHECK ".center(80, "="))
>>     print("="*80)
>>
>>     app = create_app()
>>     with app.app_context():
>>         inspector = inspect(db.engine)
>>
>>         # 1. Check users table
>>         print("\n📋 1. USERS TABLE:")
>>         print("-" * 40)
>>         users_cols = inspector.get_columns('users')
>>         for col in users_cols:
>>             if col['name'] in ['id', 'public_id']:
>>                 print(f"   {col['name']}: {col['type']}")
>>
>>         # 2. Check accounts table
>>         print("\n📋 2. ACCOUNTS TABLE:")
>>         print("-" * 40)
>>         if 'accounts' in inspector.get_table_names():
>>             accounts_cols = inspector.get_columns('accounts')
>>             for col in accounts_cols:
>>                 if col['name'] in ['id', 'user_id']:
>>                     print(f"   {col['name']}: {col['type']}")
>>         else:
>>             print("   ⚠️ 'accounts' table not found")
>>
>>         # 3. Check transactions table
>>         print("\n📋 3. TRANSACTIONS TABLE:")
>>         print("-" * 40)
>>         if 'transactions' in inspector.get_table_names():
>>             trans_cols = inspector.get_columns('transactions')
>>             for col in trans_cols:
>>                 if col['name'] in ['id', 'user_id', 'account_id']:
>>                     print(f"   {col['name']}: {col['type']}")
>>         else:
>>             print("   ⚠️ 'transactions' table not found")
>>
>>         # 4. Check foreign keys
>>         print("\n🔗 4. FOREIGN KEY RELATIONSHIPS:")
>>         print("-" * 40)
>>         result = db.session.execute(text("""
>>             SELECT
>>                 tc.table_name,
>>                 kcu.column_name,
>>                 ccu.table_name AS foreign_table,
>>                 ccu.column_name AS foreign_column
>>             FROM information_schema.table_constraints tc
>>             JOIN information_schema.key_column_usage kcu
>>                 ON tc.constraint_name = kcu.constraint_name
>>             JOIN information_schema.constraint_column_usage ccu
>>                 ON ccu.constraint_name = tc.constraint_name
>>             WHERE tc.constraint_type = 'FOREIGN KEY'
>>                 AND tc.table_name IN ('accounts', 'transactions')
>>         """))
>>         found = False
>>         for row in result:
>>             found = True
>>             print(f"   {row[0]}.{row[1]} → {row[2]}.{row[3]}")
>>         if not found:
>>             print("   No foreign keys found in accounts/transactions")
>>
>>         # 5. Summary
>>         print("\n📝 5. SUMMARY:")
>>         print("-" * 40)
>>
>>         # Check user ID types
>>         user_id_type = None
>>         user_public_id_type = None
>>         for col in users_cols:
>>             if col['name'] == 'id':
>>                 user_id_type = str(col['type'])
>>             if col['name'] == 'public_id':
>>                 user_public_id_type = str(col['type'])
>>
>>         is_correct = True
>>         if user_id_type and 'BIGINT' not in user_id_type.upper():
>>             print(f"   ⚠️ User.id is {user_id_type} - should be BIGINT")
>>             is_correct = False
>>         else:
>>             print(f"   ✅ User.id is {user_id_type} (correct)")
>>
>>         if user_public_id_type and 'VARCHAR' not in user_public_id_type.upper():
>>             print(f"   ⚠️ User.public_id is {user_public_id_type} - should be VARCHAR")
>>             is_correct = False
>>         else:
>>             print(f"   ✅ User.public_id is {user_public_id_type} (correct)")
>>
>>         print("\n" + "="*80)
>>         if is_correct:
>>             print(" ✅ YOUR DATABASE SCHEMA IS CORRECT! ".center(80, "="))
>>             print("""
>>     User.id = BIGINT (internal, for FK relationships)
>>     User.public_id = UUID/VARCHAR (external, for APIs)
>>     Account.user_id = BIGINT FK to User.id
>>
>>     This matches the Identity Separation Rule!
>>             """)
>>         else:
>>             print(" ⚠️ YOUR DATABASE SCHEMA NEEDS ATTENTION ".center(80, "="))
>>
>>         print("="*80)
>>
>> except Exception as e:
>>     print(f"\n❌ Error: {e}")
>>     print("\nMake sure you're running this from the project root with venv activated.")
>> "@ | Out-File -FilePath check_identity.py -Encoding utf8
(.venv) PS C:\Users\ADMIN\Desktop\afcon360_app> 
(.venv) PS C:\Users\ADMIN\Desktop\afcon360_app> python check_identity.py
Settings routes registered to events blueprint

================================================================================
====================== IDENTITY SEPARATION DATABASE CHECK ======================
================================================================================
2026-05-03 17:21:38,882 [INFO] root: Redis connected for sessions using existing client at redis://localhost:6379/0
2026-05-03 17:21:40,924 [INFO] root: Redis connected for rate limiting at redis://localhost:6379/0
2026-05-03 17:21:40,953 [INFO] app: 🛡️ IDGuard enabled with 1 String FK exceptions
2026-05-03 17:21:40,953 [INFO] app: âœ… IDGuard initialized for runtime ID mixing protection
2026-05-03 17:21:41,022 [DEBUG] app: Module app.org.routes not available - blueprint org_bp skipped
2026-05-03 17:21:41,108 [INFO] app.events.signal_handlers: Events module signal handlers connected
2026-05-03 17:21:41,108 [INFO] app: Events module signal handlers connected
2026-05-03 17:21:41,116 [WARNING] app: Organization blueprint not found: No module named 'app.org'
2026-05-03 17:21:41,151 [INFO] app.transport.api.routes: ✅ Transport API resources registered (32 endpoints)
2026-05-03 17:21:41,159 [INFO] app: ✅ Transport API initialized — /api/transport/* routes live
2026-05-03 17:21:41,159 [INFO] app: ✅ Transport module initialized (Deep Lazy)
2026-05-03 17:21:41,238 [INFO] app: âœ… IDGuard CLI commands registered
2026-05-03 17:21:41,238 [INFO] app.events.signal_handlers: Events module signal handlers connected
2026-05-03 17:21:41,238 [INFO] app: âœ… Event signal handlers connected
2026-05-03 17:21:41,318 [INFO] app: âœ… transactions.client_request_id unique index present
2026-05-03 17:21:41,500 [INFO] app: âœ… App factory completed in 4.67 seconds

📋 1. USERS TABLE:
----------------------------------------
   public_id: VARCHAR(64)
   id: BIGINT

📋 2. ACCOUNTS TABLE:
----------------------------------------
   id: UUID
   user_id: BIGINT

📋 3. TRANSACTIONS TABLE:
----------------------------------------
   id: UUID
   user_id: BIGINT
   account_id: UUID

🔗 4. FOREIGN KEY RELATIONSHIPS:
----------------------------------------
   accounts.user_id → users.id
   transactions.account_id → accounts.id
   transactions.recipient_user_id → users.id
   transactions.user_id → users.id

📝 5. SUMMARY:
----------------------------------------
   ✅ User.id is BIGINT (correct)
   ✅ User.public_id is VARCHAR(64) (correct)

================================================================================
====================== ✅ YOUR DATABASE SCHEMA IS CORRECT! ======================

    User.id = BIGINT (internal, for FK relationships)
    User.public_id = UUID/VARCHAR (external, for APIs)
    Account.user_id = BIGINT FK to User.id

    This matches the Identity Separation Rule!

================================================================================
(.venv) PS C:\Users\ADMIN\Desktop\afcon360_app> 

=======================🔍 IDENTITY CREATION DEMONSTRATION========================

Following Obed through the system from scratch...


────────────────────────────────────────────────────────────────────────────────
📝 STEP 1: Obed submits registration form
────────────────────────────────────────────────────────────────────────────────
   Obed enters:
   - Name: Obed
   - Email: obed@example.com
   - Phone: +256700000000
   - Password: ******

   ✅ Database creates: internal_user_id = 92240
      → This is automatic from PostgreSQL's BIGSERIAL/SEQUENCE
      → NEVER exposed to Obed or any API

   ✅ Application creates: public_id = f9bc209a-5a1e-4eec-add6-c24fff80e78a
      → Generated by: python's uuid.uuid4() function
      → This is what APIs and frontend will use

   💾 Database record saved:
      INSERT INTO users (id, public_id, name, email, phone)
      VALUES (92240, 'f9bc209a-5a1e-4eec-add6-c24fff80e78a', 'Obed', 'obed@example.com', '+256700000000')

────────────────────────────────────────────────────────────────────────────────
📝 STEP 2: Obed creates a wallet account
────────────────────────────────────────────────────────────────────────────────
   Obed clicks: 'Create Wallet'
   Selects currency: USD

   ✅ Wallet Service creates: account_id = 66841f33-b418-4521-acb7-568addbb2490
      → Generated when Obed first creates a wallet
      → This is separate from his user identity

   💾 Wallet record saved:
      INSERT INTO accounts (id, user_id, currency, balance)
      VALUES ('66841f33-b418-4521-acb7-568addbb2490', 92240, 'USD', 0.00)

      🔗 Foreign key: accounts.user_id = 92240 → users.id
         → Links the wallet to Obed's internal ID

================================================================================
================= HOW OBED GETS HIS IDENTITIES - STEP BY STEP ==================
================================================================================

================================================================================
STEP 1: Database User ID Creation
================================================================================
📝 Description: PostgreSQL automatically generates a sequential BIGINT when INSERT happens
🏷️  Identity Type: INTERNAL User ID (BIGINT)
🔑 Value: 92240
⚙️  Generated By: PostgreSQL Database (SERIAL/BIGSERIAL column)

================================================================================
STEP 2: External User ID Creation
================================================================================
📝 Description: Flask application generates UUID4 for safe API exposure
🏷️  Identity Type: EXTERNAL User ID (UUID)
🔑 Value: f9bc209a-5a1e-4eec-add6-c24fff80e78a
⚙️  Generated By: Python's uuid.uuid4() in the application layer
⏱️  Time from previous step: 0.5 seconds

================================================================================
STEP 3: Wallet Account ID Creation
================================================================================
📝 Description: When Obed creates his first wallet, system generates a new UUID for the account
🏷️  Identity Type: WALLET Account ID (UUID)
🔑 Value: 66841f33-b418-4521-acb7-568addbb2490
⚙️  Generated By: Application's wallet creation service (uuid.uuid4())
⏱️  Time from previous step: 1.0 seconds

================================================================================
======================= SUMMARY: OBED'S THREE IDENTITIES =======================
================================================================================

    ┌─────────────────┬──────────────────────────────────┬─────────────────────────────┐
    │ Identity        │ Value for Obed                   │ When Created                │
    ├─────────────────┼──────────────────────────────────┼─────────────────────────────┤
    │ Database Obed   │ 92240 │ At registration (PostgreSQL)    │
    │ API Obed        │ f9bc209a-5a1e-4eec-add6-c24fff80e78a │ At registration (Application)   │
    │ Wallet Obed     │ 66841f33-b418-4521-acb7-568addbb2490 │ When first wallet is created    │
    └─────────────────┴──────────────────────────────────┴─────────────────────────────┘


================================================================================
======================= 🎯 WHY THREE SEPARATE IDENTITIES? =======================
================================================================================


    1️⃣  Database Obed (ID: 92240)
        └── Purpose: Fast database joins, foreign keys, indexing
        └── Generated by: PostgreSQL AUTO_INCREMENT
        └── Never exposed: Only internal system use

    2️⃣  API Obed (ID: 5c0bdc66-...)
        └── Purpose: URLs, API responses, session cookies
        └── Generated by: Python's uuid.uuid4()
        └── Always exposed: Safe, non-guessable

    3️⃣  Wallet Obed (ID: 77a85b56-...)
        └── Purpose: Financial account identification
        └── Generated by: Application when wallet is created
        └── Can be exposed: Payment references, transaction history

    WHY CAN'T WE USE JUST ONE?
    ─────────────────────────────────────────────────────────────────
    ❌ If we only used 92240:
       - Hackers could guess user IDs (1,2,3,4...)
       - Sequential IDs expose user count
       - Not safe for URLs

    ❌ If we only used UUID everywhere:
       - Foreign keys would be slower (UUID vs BIGINT)
       - Database joins would be less efficient
       - More storage space (16 bytes vs 8 bytes)

    ✅ Using BOTH gives us:
       - Security (non-guessable UUIDs for APIs)
       - Performance (BIGINT for database joins)
       - Separation of concerns (User vs Account)


================================================================================
===================== 📝 ACTUAL CODE THAT CREATES THESE IDS =====================
================================================================================

    # 1. Database Model (app/identity/models/user.py)
    class User(db.Model):
        __tablename__ = 'users'

        # PostgreSQL automatically generates this BIGINT
        id = Column(BigInteger, primary_key=True)  # ← Auto-increment

        # Application generates this UUID
        public_id = Column(String(64), unique=True,
                          default=lambda: str(uuid.uuid4()))  # ← Python generates

    # 2. When Obed registers (in your registration code)
    @app.route('/register', methods=['POST'])
    def register():
        # Create user object
        user = User(
            name=request.form['name'],
            email=request.form['email'],
            phone=request.form['phone']
        )
        # user.id will be assigned by PostgreSQL after INSERT
        # user.public_id is auto-generated by the default=lambda above

        db.session.add(user)
        db.session.flush()  # This assigns user.id

        print(f"Internal ID: {user.id}")      # 92240 (from DB)
        print(f"External ID: {user.public_id}") # UUID (from Python)

        return jsonify({'user_id': user.public_id})  # ← Return ONLY the UUID!

    # 3. When Obed creates a wallet (in your wallet service)
    def create_wallet(user_id, currency='USD'):
        # user_id here is the INTERNAL BIGINT (92240)

        account = Account(
            id=str(uuid.uuid4()),  # ← Generate new UUID for account
            user_id=user_id,       # ← Link to user's internal ID
            currency=currency,
            balance=0
        )

        db.session.add(account)
        db.session.commit()

        return account.id  # Returns the account UUID


================================================================================
====================== 🔄 HOW IDS FLOW THROUGH AN API CALL ======================
================================================================================

    Obed wants to check his wallet balance:

    ┌─────────────────────────────────────────────────────────────────────────────┐
    │ 1. Frontend (React/Vue)                                                     │
    │    fetch('/api/wallet/balance', {                                           │
    │        headers: { 'Authorization': 'Bearer <session_token>' }               │
    │    })                                                                       │
    │    Session token contains: user.public_id                                   │
    └─────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
    ┌─────────────────────────────────────────────────────────────────────────────┐
    │ 2. Flask Route (app/wallet/api/wallet_api.py)                              │
    │                                                                             │
    │    @wallet_bp.route('/balance')                                             │
    │    @login_required                                                          │
    │    def get_balance():                                                       │
    │        # current_user is loaded via Flask-Login                             │
    │        # It uses user.get_id() which returns public_id                      │
    │        public_id = current_user.public_id  # ← '5c0bdc66-...'              │
    │                                                                             │
    │        # Convert to internal ID for DB query                               │
    │        user = User.get_by_public_id(public_id)                             │
    │        internal_id = user.id  # ← 92240                                    │
    │                                                                             │
    │        # Query using internal ID for performance                          │
    │        account = Account.query.filter_by(user_id=internal_id).first()      │
    │        # SQL: SELECT * FROM accounts WHERE user_id = 92240                 │
    │                                                                             │
    │        return jsonify({                                                     │
    │            'account_id': account.id,  # ← '77a85b56-...' (UUID)            │
    │            'balance': account.balance                                       │
    │        })                                                                   │
    └─────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
    ┌─────────────────────────────────────────────────────────────────────────────┐
    │ 3. API Response (What Obed's app receives)                                 │
    │                                                                             │
    │    {                                                                        │
    │        "account_id": "77a85b56-c8f0-4e72-97d1-3d174b595eea",              │
    │        "balance": "74.50"                                                   │
    │    }                                                                        │
    │                                                                             │
    │    Notice: Obed's internal ID (92240) NEVER appears in the response!      │
    └─────────────────────────────────────────────────────────────────────────────┘


================================================================================
====================== ✅ SUMMARY: OBED'S THREE IDENTITIES ======================
================================================================================

    ┌──────────────────┬────────────────────────────┬────────────────────────────┐
    │ Identity         │ When Created               │ How Created                │
    ├──────────────────┼────────────────────────────┼────────────────────────────┤
    │ Database Obed    │ At registration INSERT     │ PostgreSQL AUTO_INCREMENT  │
    │ (92240)          │                            │ (BIGSERIAL)                │
    ├──────────────────┼────────────────────────────┼────────────────────────────┤
    │ API Obed         │ At registration (Python)   │ uuid.uuid4()               │
    │ (UUID)           │                            │                            │
    ├──────────────────┼────────────────────────────┼────────────────────────────┤
    │ Wallet Obed      │ When first wallet created  │ uuid.uuid4()               │
    │ (Account UUID)   │                            │                            │
    └──────────────────┴────────────────────────────┴────────────────────────────┘

    🔑 Key Insight:
       The system doesn't "give out" these identities - they are CREATED
       at different times for different purposes:

       - 92240: Created by PostgreSQL for database efficiency
       - UUID: Created by Python for API security
       - Account UUID: Created by Wallet service for financial tracking

(.venv) PS C:\Users\ADMIN\Desktop\afcon360_app> 
