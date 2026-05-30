                                                                                                                                                                                  
<<<<<<< SEARCH                                                                                                                                                                    
=======                                                                                                                                                                           
# AFCON360 Wallet System - Complete User Flow & Policy Documentation                                                                                                              
                                                                                                                                                                                  
## Document Purpose                                                                                                                                                               
This document describes the complete wallet system flow, rules, and policies for:                                                                                                 
- **End Users** - How they create and use their wallet                                                                                                                            
- **Banking Partners** - Security, compliance, and audit controls                                                                                                                 
- **Investors** - Business logic and feature completeness                                                                                                                         
- **QA/Testing** - Verification criteria for each flow                                                                                                                            
                                                                                                                                                                                  
---                                                                                                                                                                               
                                                                                                                                                                                  
## 1. User Identity Architecture                                                                                                                                                  
                                                                                                                                                                                  
### 1.1 Dual Identity System                                                                                                                                                      
                                                                                                                                                                                  
| Identity Type | Storage | Visibility | Purpose | Example |                                                                                                                      
|---|---|---|---|---|                                                                                                                                                             
| Internal ID | BIGINT (Database) | ❌ NEVER exposed | Database joins, foreign keys, performance | 92240 |                                                                        
| External ID | UUID (String) | ✅ Always exposed | API responses, URLs, session cookies | 5c0bdc66-4388-45af-b008-d5816c40a4cc |                                                 
                                                                                                                                                                                  
### 1.2 Account Identity                                                                                                                                                          
                                                                                                                                                                                  
| Element | Type | Purpose |                                                                                                                                                      
|---|---|---|                                                                                                                                                                     
| Account ID | UUID | Financial account identifier (safe to expose) |                                                                                                             
| User ID (FK) | BIGINT | Links account to user (internal only) |                                                                                                                 
                                                                                                                                                                                  
**Rule:** A user can have ONE wallet account. This is enforced at the database level with a unique constraint.                                                                    
                                                                                                                                                                                  
---                                                                                                                                                                               
                                                                                                                                                                                  
## 2. Complete Wallet Creation & Onboarding Flow                                                                                                                                  
                                                                                                                                                                                  
### 2.1 Pre-Creation Requirements                                                                                                                                                 
                                                                                                                                                                                  
The system checks these requirements **BEFORE** allowing wallet creation:                                                                                                         
                                                                                                                                                                                  
| Requirement | Check | Action if Missing |                                                                                                                                       
|---|---|---|                                                                                                                                                                     
| Email verified | ✅ | Show "Verify Email" link |                                                                                                                                
| Phone verified | ✅ | Show "Verify Phone" link |                                                                                                                                
| Age 18+ | ✅ (if DOB available) | Block creation, show message |                                                                                                                
| Country allowed | ✅ | Block if restricted country |                                                                                                                            
| Terms accepted | ✅ | Checkbox must be checked |                                                                                                                                
                                                                                                                                                                                  
**Restricted Countries:** IR, KP, SY, CU, MM                                                                                                                                      
                                                                                                                                                                                  
### 2.2 Pre-Creation Popup (Mandatory)                                                                                                                                            
                                                                                                                                                                                  
**Trigger:** User clicks "Create Wallet" button                                                                                                                                   
                                                                                                                                                                                  
**Content shown to user:**                                                                                                                                                        
- Requirements checklist                                                                                                                                                          
- Initial limits (Tier 0)                                                                                                                                                         
- Security requirements                                                                                                                                                           
- Estimated time (5-10 minutes)                                                                                                                                                   
                                                                                                                                                                                  
**User must click:** "I Understand, Proceed"                                                                                                                                      
                                                                                                                                                                                  
### 2.3 Wallet Creation                                                                                                                                                           
                                                                                                                                                                                  
**Trigger:** User clicks "I Understand, Proceed" in popup                                                                                                                         
                                                                                                                                                                                  
**System Actions:**                                                                                                                                                               
1. Generate unique Account ID (UUID)                                                                                                                                              
2. Link to User ID (BIGINT foreign key)                                                                                                                                           
3. Set initial status: `verified = False` (pending activation)                                                                                                                    
4. Set currency (default: UGX)                                                                                                                                                    
5. Set zero balances                                                                                                                                                              
6. Create audit log entry                                                                                                                                                         
7. Send welcome notification (SMS/Email)                                                                                                                                          
                                                                                                                                                                                  
**Resulting Status:** Wallet exists but **NOT activated**                                                                                                                         
                                                                                                                                                                                  
### 2.4 Wallet Activation                                                                                                                                                         
                                                                                                                                                                                  
**Trigger:** User navigates to wallet after creation                                                                                                                              
                                                                                                                                                                                  
**Activation Page Shows:**                                                                                                                                                        
- Wallet details (Account ID, currency, creation date)                                                                                                                            
- Next steps (3 steps displayed)                                                                                                                                                  
- Terms & Conditions acceptance checkbox                                                                                                                                          
                                                                                                                                                                                  
**Next Steps Displayed:**                                                                                                                                                         
                                                                                                                                                                                  
| Step | Description | Required For |                                                                                                                                             
|---|---|---|                                                                                                                                                                     
| 1 | Accept Terms & Conditions | Full access |                                                                                                                                   
| 2 | Set Transaction PIN | Sending money |                                                                                                                                       
| 3 | Complete KYC Verification | Higher limits |                                                                                                                                 
                                                                                                                                                                                  
**After Activation:** `verified = True` - User can now use wallet features                                                                                                        
                                                                                                                                                                                  
---                                                                                                                                                                               
                                                                                                                                                                                  
## 3. KYC Tiers & Feature Access                                                                                                                                                  
                                                                                                                                                                                  
### 3.1 Tier Definitions                                                                                                                                                          
                                                                                                                                                                                  
| Tier | Name | KYC Level | Requirements | User Experience |                                                                                                                      
|---|---|---|---|---|                                                                                                                                                             
| Tier 0 | Unverified | 0 | Email + Phone verified | Can create wallet, receive money only |                                                                                      
| Tier 1 | Basic | 1 | ID verified (passport/national ID) | Can send, receive, withdraw (limited) |                                                                               
| Tier 2 | Enhanced | 2 | Address + ID verified | Higher limits, international transfers |                                                                                        
| Tier 3 | Full | 3 | Source of funds verified | Unlimited access |                                                                                                               
                                                                                                                                                                                  
### 3.2 Feature Access by Tier                                                                                                                                                    
                                                                                                                                                                                  
| Feature | Tier 0 | Tier 1 | Tier 2 | Tier 3 |                                                                                                                                   
|---|---|---|---|---|                                                                                                                                                             
| Create Wallet | ✅ | ✅ | ✅ | ✅ |                                                                                                                                             
| Activate Wallet | ✅ | ✅ | ✅ | ✅ |                                                                                                                                           
| View Dashboard | ✅ | ✅ | ✅ | ✅ |                                                                                                                                            
| View Transaction History | ✅ | ✅ | ✅ | ✅ |                                                                                                                                  
| Receive Money | ✅ | ✅ | ✅ | ✅ |                                                                                                                                             
| Deposit Money | ✅ | ✅ | ✅ | ✅ |                                                                                                                                             
| Send Money | ❌ | ✅ | ✅ | ✅ |                                                                                                                                                
| Withdraw Money | ❌ | ✅ | ✅ | ✅ |                                                                                                                                            
| Request Payout | ❌ | ✅ | ✅ | ✅ |                                                                                                                                            
| View Commissions | ❌ | ✅ | ✅ | ✅ |                                                                                                                                          
| International Transfer | ❌ | ❌ | ✅ | ✅ |                                                                                                                                    
| Bulk Payment | ❌ | ❌ | ❌ | ✅ |                                                                                                                                              
| Merchant Account | ❌ | ❌ | ✅ | ✅ |                                                                                                                                          
| API Access | ❌ | ❌ | ✅ | ✅ |                                                                                                                                                
                                                                                                                                                                                  
### 3.3 Transaction Limits by Tier                                                                                                                                                
                                                                                                                                                                                  
| Limit | Tier 0 | Tier 1 | Tier 2 | Tier 3 |                                                                                                                                     
|---|---|---|---|---|                                                                                                                                                             
| Daily Deposit | UGX 1,000,000 | UGX 10,000,000 | UGX 50,000,000 | Unlimited |                                                                                                   
| Daily Withdrawal | UGX 500,000 | UGX 5,000,000 | UGX 20,000,000 | Unlimited |                                                                                                   
| Monthly Transfer | UGX 2,000,000 | UGX 20,000,000 | UGX 100,000,000 | Unlimited |                                                                                               
| Single Transaction | UGX 500,000 | UGX 2,000,000 | UGX 10,000,000 | Unlimited |                                                                                                 
                                                                                                                                                                                  
---                                                                                                                                                                               
                                                                                                                                                                                  
## 4. Dynamic Navigation Rules                                                                                                                                                    
                                                                                                                                                                                  
### 4.1 Sidebar Menu Items - When They Appear                                                                                                                                     
                                                                                                                                                                                  
| Menu Item | Shows When |                                                                                                                                                        
|---|---|                                                                                                                                                                         
| Dashboard | Always |                                                                                                                                                            
| Create Wallet | Only when user has NO wallet |                                                                                                                                  
| Deposit Funds | Only when wallet exists and is activated |                                                                                                                      
| Send Funds | Only when wallet exists, activated, AND KYC Tier ≥ 1 |                                                                                                             
| Withdraw Funds | Only when wallet exists, activated, AND KYC Tier ≥ 1 |                                                                                                         
| Transaction History | Only when wallet exists |                                                                                                                                 
| FX Rates | Always |                                                                                                                                                             
| Agent Payout | Only when wallet exists, activated, AND KYC Tier ≥ 1 |                                                                                                           
| Compliance | Always |                                                                                                                                                           
| Settings | Always |                                                                                                                                                             
| Terms & Conditions | Always |                                                                                                                                                   
                                                                                                                                                                                  
### 4.2 Action Buttons - What Shows Where                                                                                                                                         
                                                                                                                                                                                  
| Button | Shows When | Click Action |                                                                                                                                            
|---|---|---|                                                                                                                                                                     
| Create Wallet | No wallet exists | Opens creation popup |                                                                                                                       
| Activate Wallet | Wallet exists but not activated | Goes to activation page |                                                                                                   
| Deposit | Wallet activated | Goes to deposit form |                                                                                                                             
| Send | Wallet activated + KYC Tier ≥ 1 | Goes to send form |                                                                                                                    
| Withdraw | Wallet activated + KYC Tier ≥ 1 | Goes to withdraw form |                                                                                                            
                                                                                                                                                                                  
### 4.3 Informational Banners                                                                                                                                                     
                                                                                                                                                                                  
| Banner Type | Shows When | Content |                                                                                                                                            
|---|---|---|                                                                                                                                                                     
| Info | No wallet | "Create your wallet to start..." |                                                                                                                           
| Warning | Wallet not activated | "Please activate your wallet..." |                                                                                                             
| Warning | KYC pending | "Complete KYC verification..." |                                                                                                                        
| Info | PIN not set | "Set transaction PIN for security..." |                                                                                                                    
                                                                                                                                                                                  
---                                                                                                                                                                               
                                                                                                                                                                                  
## 5. Wallet Operations Flow                                                                                                                                                      
                                                                                                                                                                                  
### 5.1 Deposit Money                                                                                                                                                             
                                                                                                                                                                                  
**Prerequisites:** Wallet activated (any tier)                                                                                                                                    
                                                                                                                                                                                  
**Flow:**                                                                                                                                                                         
1. User clicks "Deposit" button                                                                                                                                                   
2. System checks: `can_deposit = True` (any tier)                                                                                                                                 
3. User enters amount and selects currency                                                                                                                                        
4. System validates amount against daily limit                                                                                                                                    
5. System creates pending transaction                                                                                                                                             
6. System credits wallet balance                                                                                                                                                  
7. System creates ledger entry (CREDIT)                                                                                                                                           
8. System sends confirmation notification                                                                                                                                         
9. User sees updated balance                                                                                                                                                      
                                                                                                                                                                                  
### 5.2 Send Money (Transfer)                                                                                                                                                     
                                                                                                                                                                                  
**Prerequisites:** Wallet activated + KYC Tier ≥ 1                                                                                                                                
                                                                                                                                                                                  
**Flow:**                                                                                                                                                                         
1. User clicks "Send" button                                                                                                                                                      
2. System checks: `can_send = True` (Tier ≥ 1)                                                                                                                                    
3. User enters recipient ID, amount, currency                                                                                                                                     
4. System validates recipient has wallet                                                                                                                                          
5. System validates sender balance sufficient                                                                                                                                     
6. System validates amount against limits                                                                                                                                         
7. User enters Transaction PIN                                                                                                                                                    
8. System verifies PIN                                                                                                                                                            
9. System creates transaction (within database transaction)                                                                                                                       
10. System debits sender, credits receiver                                                                                                                                        
11. System creates TWO ledger entries (DEBIT + CREDIT)                                                                                                                            
12. System sends notifications to both parties                                                                                                                                    
13. Both users see updated balances                                                                                                                                               
                                                                                                                                                                                  
### 5.3 Withdraw Money                                                                                                                                                            
                                                                                                                                                                                  
**Prerequisites:** Wallet activated + KYC Tier ≥ 1                                                                                                                                
                                                                                                                                                                                  
**Flow:**                                                                                                                                                                         
1. User clicks "Withdraw" button                                                                                                                                                  
2. System checks: `can_withdraw = True` (Tier ≥ 1)                                                                                                                                
3. User enters amount and selects withdrawal method                                                                                                                               
4. System validates balance sufficient                                                                                                                                            
5. System validates amount against daily limit                                                                                                                                    
6. System creates withdrawal request                                                                                                                                              
7. System debits wallet balance                                                                                                                                                   
8. System creates ledger entry (DEBIT)                                                                                                                                            
9. System initiates payout to external account                                                                                                                                    
10. User receives confirmation                                                                                                                                                    
                                                                                                                                                                                  
### 5.4 View Transaction History                                                                                                                                                  
                                                                                                                                                                                  
**Prerequisites:** Wallet exists (any tier)                                                                                                                                       
                                                                                                                                                                                  
**Flow:**                                                                                                                                                                         
1. User clicks "Transaction History" button                                                                                                                                       
2. System fetches all transactions where user is sender OR recipient                                                                                                              
3. System displays:                                                                                                                                                               
   - Transaction type (Deposit/Send/Withdraw/Receive)                                                                                                                             
   - Amount and currency                                                                                                                                                          
   - Status (Completed/Pending/Failed)                                                                                                                                            
   - Date and time                                                                                                                                                                
   - Counterparty (if transfer)                                                                                                                                                   
                                                                                                                                                                                  
---                                                                                                                                                                               
                                                                                                                                                                                  
## 6. Security Policies                                                                                                                                                           
                                                                                                                                                                                  
### 6.1 Transaction PIN Policy                                                                                                                                                    
                                                                                                                                                                                  
| Rule | Value |                                                                                                                                                                  
|---|---|                                                                                                                                                                         
| PIN Length | 4-6 digits only |                                                                                                                                                  
| Storage | Hashed (never stored in plain text) |                                                                                                                                 
| Max Failed Attempts | 5 attempts |                                                                                                                                              
| Lockout Duration | 15 minutes |                                                                                                                                                 
| PIN Required For | All transfer operations |                                                                                                                                    
                                                                                                                                                                                  
### 6.2 Session Security                                                                                                                                                          
                                                                                                                                                                                  
| Rule | Implementation |                                                                                                                                                         
|---|---|                                                                                                                                                                         
| Session ID | Uses public_id (UUID), never internal BIGINT |                                                                                                                     
| CSRF Protection | Required for all state-changing operations |                                                                                                                  
| Idempotency | X-Idempotency-Key header required for deposits/transfers |                                                                                                        
                                                                                                                                                                                  
### 6.3 Audit Trail                                                                                                                                                               
                                                                                                                                                                                  
All financial operations are logged with:                                                                                                                                         
                                                                                                                                                                                  
| Field | Description |                                                                                                                                                           
|---|---|                                                                                                                                                                         
| Transaction ID | Unique UUID |                                                                                                                                                  
| Actor ID | User ID (internal) |                                                                                                                                                 
| Action Type | deposit/withdraw/transfer |                                                                                                                                       
| Amount | Transaction amount |                                                                                                                                                   
| Currency | Currency code |                                                                                                                                                      
| Before State | Balance before operation |                                                                                                                                       
| After State | Balance after operation |                                                                                                                                         
| IP Address | Client IP |                                                                                                                                                        
| Timestamp | UTC timestamp |                                                                                                                                                     
                                                                                                                                                                                  
---                                                                                                                                                                               
                                                                                                                                                                                  
## 7. Compliance & Regulatory Policies                                                                                                                                            
                                                                                                                                                                                  
### 7.1 AML/CFT Checks                                                                                                                                                            
                                                                                                                                                                                  
| Check | Trigger | Action |                                                                                                                                                      
|---|---|---|                                                                                                                                                                     
| Daily reporting threshold | Transaction ≥ UGX 10,000,000 | Notify compliance |                                                                                                  
| Structuring detection | Multiple transactions near threshold | Flag for review |                                                                                                
| Rapid succession | 5+ transactions in 5 minutes | Manual review required |                                                                                                      
| Sanctions screening | Every transaction | Block if match found |                                                                                                                
                                                                                                                                                                                  
### 7.2 KYC Enforcement                                                                                                                                                           
                                                                                                                                                                                  
| Operation | Min Tier Required |                                                                                                                                                 
|---|---|                                                                                                                                                                         
| Create wallet | Tier 0 (any) |                                                                                                                                                  
| Activate wallet | Tier 0 |                                                                                                                                                      
| Deposit | Tier 0 |                                                                                                                                                              
| Send money | Tier 1 |                                                                                                                                                           
| Withdraw | Tier 1 |                                                                                                                                                             
| Request payout | Tier 1 |                                                                                                                                                       
| International transfer | Tier 2 |                                                                                                                                               
                                                                                                                                                                                  
### 7.3 Audit Requirements                                                                                                                                                        
                                                                                                                                                                                  
Every wallet event is audited:                                                                                                                                                    
- Wallet creation → Audit log                                                                                                                                                     
- Wallet activation → Audit log                                                                                                                                                   
- Deposit → Financial audit + API audit                                                                                                                                           
- Transfer → Financial audit + API audit                                                                                                                                          
- Withdrawal → Financial audit + API audit                                                                                                                                        
- KYC status change → Security audit                                                                                                                                              
- Admin action → Admin audit log                                                                                                                                                  
                                                                                                                                                                                  
---                                                                                                                                                                               
                                                                                                                                                                                  
## 8. Error Handling & User Messages                                                                                                                                              
                                                                                                                                                                                  
### 8.1 Wallet Creation Errors                                                                                                                                                    
                                                                                                                                                                                  
| Error | User Message | Action |                                                                                                                                                 
|---|---|---|                                                                                                                                                                     
| Email not verified | "Please verify your email address first." | Show verify link |                                                                                             
| Phone not verified | "Please verify your phone number first." | Show verify link |                                                                                              
| Age under 18 | "You must be 18 or older." | Block |                                                                                                                             
| Country restricted | "Wallet not available in your country." | Block |                                                                                                          
| Terms not accepted | "You must accept Terms & Conditions." | Show checkbox |                                                                                                    
                                                                                                                                                                                  
### 8.2 Transaction Errors                                                                                                                                                        
                                                                                                                                                                                  
| Error | User Message |                                                                                                                                                          
|---|---|                                                                                                                                                                         
| Insufficient balance | "Insufficient funds. Available: X" |                                                                                                                     
| Daily limit exceeded | "Daily limit reached. Available: X" |                                                                                                                    
| Invalid PIN | "Incorrect PIN. X attempts remaining." |                                                                                                                          
| PIN locked | "PIN locked for 15 minutes." |                                                                                                                                     
| Recipient no wallet | "Recipient has no wallet. Ask them to create one." |                                                                                                      
                                                                                                                                                                                  
---                                                                                                                                                                               
                                                                                                                                                                                  
## 9. Testing Verification Checklist                                                                                                                                              
                                                                                                                                                                                  
### 9.1 Wallet Creation Flow                                                                                                                                                      
                                                                                                                                                                                  
- [ ] User without wallet sees "Create Wallet" in sidebar                                                                                                                         
- [ ] Other wallet features are hidden                                                                                                                                            
- [ ] Clicking "Create Wallet" shows pre-creation popup                                                                                                                           
- [ ] Popup shows requirements, limits, security info                                                                                                                             
- [ ] User must click "I Understand" to proceed                                                                                                                                   
- [ ] Terms checkbox must be checked                                                                                                                                              
- [ ] Emails/phones must be verified before creation                                                                                                                              
- [ ] Wallet created with status "pending activation"                                                                                                                             
- [ ] Welcome notification sent                                                                                                                                                   
- [ ] Redirect to activation page                                                                                                                                                 
                                                                                                                                                                                  
### 9.2 Wallet Activation Flow                                                                                                                                                    
                                                                                                                                                                                  
- [ ] Activation page shows wallet details                                                                                                                                        
- [ ] Shows 3 next steps                                                                                                                                                          
- [ ] Terms must be accepted                                                                                                                                                      
- [ ] After activation, `verified = True`                                                                                                                                         
- [ ] User can now access wallet features                                                                                                                                         
                                                                                                                                                                                  
### 9.3 Feature Gating                                                                                                                                                            
                                                                                                                                                                                  
- [ ] User with Tier 0 can only deposit (not send/withdraw)                                                                                                                       
- [ ] User with Tier 1 can send and withdraw                                                                                                                                      
- [ ] User with Tier 2 sees international transfer option                                                                                                                         
- [ ] User with Tier 3 sees all features                                                                                                                                          
- [ ] Limits decrease/hide when tier changes                                                                                                                                      
                                                                                                                                                                                  
### 9.4 Dynamic Sidebar                                                                                                                                                           
                                                                                                                                                                                  
- [ ] Menu items appear/disappear based on wallet status                                                                                                                          
- [ ] No wallet → only "Create Wallet" shows                                                                                                                                      
- [ ] Wallet exists but not activated → activation banner shows                                                                                                                   
- [ ] Wallet activated → full menu shows (with tier limits)                                                                                                                       
                                                                                                                                                                                  
### 9.5 Security                                                                                                                                                                  
                                                                                                                                                                                  
- [ ] Internal user.id NEVER exposed in API responses                                                                                                                             
- [ ] public_id used in all URLs and API responses                                                                                                                                
- [ ] Transaction PIN required for transfers                                                                                                                                      
- [ ] CSRF token required for form submissions                                                                                                                                    
- [ ] Idempotency keys prevent duplicate transactions                                                                                                                             
                                                                                                                                                                                  
---                                                                                                                                                                               
                                                                                                                                                                                  
## 10. Non-Technical Summary                                                                                                                                                      
                                                                                                                                                                                  
### For Users (What to Expect)                                                                                                                                                    
                                                                                                                                                                                  
1. **Step 1: Verify** - Verify your email and phone number                                                                                                                        
2. **Step 2: Create** - Click "Create Wallet", read the popup, accept terms                                                                                                       
3. **Step 3: Activate** - Accept Terms & Conditions on activation page                                                                                                            
4. **Step 4: Secure** - Set a 4-6 digit transaction PIN                                                                                                                           
5. **Step 5: Verify KYC** - Complete identity verification to unlock higher limits                                                                                                
6. **Step 6: Use** - Deposit, send, withdraw, view transactions                                                                                                                   
                                                                                                                                                                                  
### For Banks/Partners (What We Guarantee)                                                                                                                                        
                                                                                                                                                                                  
- **Security:** Internal user IDs never exposed externally                                                                                                                        
- **Compliance:** Full audit trail for all transactions                                                                                                                           
- **KYC Enforcement:** Tier-based limits before sending/withdrawing                                                                                                               
- **AML Monitoring:** Automatic suspicious transaction detection                                                                                                                  
- **Data Protection:** Separation of user identity from financial accounts                                                                                                        
                                                                                                                                                                                  
### For Investors (Business Value)                                                                                                                                                
                                                                                                                                                                                  
- **User Experience:** Smooth onboarding with clear steps                                                                                                                         
- **Security:** Industry-standard identity separation                                                                                                                             
- **Scalability:** Can support millions of wallets                                                                                                                                
- **Compliance Ready:** All regulatory requirements addressed                                                                                                                     
- **Auditable:** Complete transaction history with immutable ledger                                                                                                               
                                                                                                                                                                                  
---                                                                                                                                                                               
                                                                                                                                                                                  
## 11. How to Verify the Implementation                                                                                                                                           
                                                                                                                                                                                  
### Automated Tests (Run with pytest)                                                                                                                                             
                                                                                                                                                                                  
```bash                                                                                                                                                                           
# Run all wallet tests                                                                                                                                                            
pytest tests/wallet/ -v                                                                                                                                                           
                                                                                                                                                                                  
# Specific test categories                                                                                                                                                        
pytest tests/wallet/test_creation.py -v      # Wallet creation flow                                                                                                               
pytest tests/wallet/test_activation.py -v    # Activation flow                                                                                                                    
pytest tests/wallet/test_limits.py -v        # Tier limits                                                                                                                        
pytest tests/wallet/test_security.py -v      # Security checks                                                                                                                    
                                                                                                                                                                                  

Manual Testing Checklist                                                                                                                                                          

                                                                         
 Test Case                      Expected Result                          
 ─────────────────────────────────────────────────────────────────────── 
 Register new user (no wallet)  See "Create Wallet" button only          
 Click "Create Wallet"          Pre-creation popup appears               
 Accept terms and create        Wallet created, redirected to activation 
 Activate wallet                Wallet activated, full menu appears      
 Try to send with Tier 0        Error message, feature hidden            
 Complete KYC Tier 1            Send/withdraw buttons appear             
 Set transaction PIN            PIN required for transfers               
 Make deposit                   Balance increases, transaction recorded  
 Make transfer                  Both balances update correctly           
                                                                         

----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------


12. Success Criteria                                                                                                                                                              

The wallet system is considered complete and ready for production when:                                                                                                           

 • ✅ User can create wallet only after email/phone verification                                                                                                                  
 • ✅ Pre-creation popup shows all requirements before creation                                                                                                                   
 • ✅ Wallet must be activated separately (terms acceptance)                                                                                                                      
 • ✅ Features auto-hide when requirements not met                                                                                                                                
 • ✅ Transaction PIN required for all transfers                                                                                                                                  
 • ✅ Internal user.id never exposed in any response                                                                                                                              
 • ✅ KYC tiers correctly gate features                                                                                                                                           
 • ✅ All financial operations are atomic and auditable                                                                                                                           
 • ✅ Limits enforced at database level (no race conditions)                                                                                                                      
 • ✅ Admin can configure limits and view audit logs                                                                                                                              

----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------


13. Issues Found & Planned Fixes                                                                                                                                                  

Issue 1: Activation Route Missing CSRF Validation                                                                                                                                 

Location: app/wallet/routes.py - wallet_activate_submit() function                                                                                                                

Description: The activation form includes {{ csrf_token }} in the template, but the route does not call validate_csrf(). This means CSRF protection is not enforced for wallet    
activation.                                                                                                                                                                       

Planned Fix:                                                                                                                                                                      

                                                                                                                                                                                  
@wallet_bp.route('/activate', methods=['POST'])                                                                                                                                   
@login_required                                                                                                                                                                   
def wallet_activate_submit():                                                                                                                                                     
    """Submit wallet activation"""                                                                                                                                                
    from flask_wtf.csrf import validate_csrf                                                                                                                                      
                                                                                                                                                                                  
    # Validate CSRF                                                                                                                                                               
    csrf_token = request.form.get('csrf_token')                                                                                                                                   
    if not csrf_token:                                                                                                                                                            
        flash('CSRF token missing', 'error')                                                                                                                                      
        return redirect(url_for('wallet.wallet_activate'))                                                                                                                        
    try:                                                                                                                                                                          
        validate_csrf(csrf_token)                                                                                                                                                 
    except Exception:                                                                                                                                                             
        flash('Invalid CSRF token', 'error')                                                                                                                                      
        return redirect(url_for('wallet.wallet_activate'))                                                                                                                        
                                                                                                                                                                                  
    # ... rest of function                                                                                                                                                        
                                                                                                                                                                                  

Issue 2: Activation Route Allows Re-Activation                                                                                                                                    

Location: app/wallet/routes.py - wallet_activate_submit() function                                                                                                                

Description: If a user submits the activation form multiple times, it will set verified=True again each time. While this doesn't cause errors, it's unnecessary and could be      
confusing.                                                                                                                                                                        

Planned Fix:                                                                                                                                                                      

                                                                                                                                                                                  
# Check if already activated                                                                                                                                                      
if account.verified:                                                                                                                                                              
    flash('Your wallet is already activated.', 'info')                                                                                                                            
    return redirect(url_for('wallet.wallet_dashboard'))                                                                                                                           
                                                                                                                                                                                  

Issue 3: requires_terms_acceptance Field Not Used                                                                                                                                 

Location: app/wallet/services/wallet_status_service.py - WalletStatus dataclass                                                                                                   

Description: The requires_terms_acceptance field is set to not is_activated but is never checked anywhere in the codebase. It should be used to show a banner or redirect to terms
acceptance.                                                                                                                                                                       

Planned Fix:                                                                                                                                                                      

 • Add a check in the middleware or dashboard to redirect users who haven't accepted terms                                                                                        
 • Or remove the field if it's not needed                                                                                                                                         

Issue 4: Missing require_payout_access Decorator Usage                                                                                                                            

Location: app/wallet/routes.py - agent_payout_history() function                                                                                                                  

Description: The agent_payout_history route uses @require_wallet_for_feature(feature=WalletFeature.VIEW_PAYOUT_HISTORY) directly instead of the @require_payout_access decorator. 
Both work identically, but for consistency it should use @require_payout_access.                                                                                                  

Planned Fix:                                                                                                                                                                      

                                                                                                                                                                                  
@wallet_bp.route('/agent/payout/history')                                                                                                                                         
@login_required                                                                                                                                                                   
@require_payout_access                                                                                                                                                            
def agent_payout_history():                                                                                                                                                       
                                                                                                                                                                                  

Issue 5: redirect_to Parameter Never Used                                                                                                                                         

Location: app/wallet/middleware/wallet_check.py - require_wallet_for_feature() function                                                                                           

Description: The redirect_to parameter is accepted but never used in the redirect logic. The redirect is hardcoded inside the function.                                           

Planned Fix:                                                                                                                                                                      

 • Either use the redirect_to parameter in the redirect logic                                                                                                                     
 • Or remove the parameter to avoid confusion                                                                                                                                     

Issue 6: Wallet Activation Template Uses action == 'verify' Logic                                                                                                                 

Location: templates/wallet/wallet_activate.html                                                                                                                                   

Description: The template checks {% if action == 'verify' %} to determine whether to show activation mode or creation mode. However, the route wallet_activate() does not pass an 
action variable to the template. This means the template always shows the creation mode (the {% else %} branch), not the activation mode.                                         

Planned Fix:                                                                                                                                                                      

                                                                                                                                                                                  
@wallet_bp.route('/activate')                                                                                                                                                     
@login_required                                                                                                                                                                   
def wallet_activate():                                                                                                                                                            
    """Wallet activation page"""                                                                                                                                                  
    try:                                                                                                                                                                          
        account = get_account(current_user.id)                                                                                                                                    
        if not account:                                                                                                                                                           
            flash('You need to create a wallet first.', 'warning')                                                                                                                
            return redirect(url_for('wallet.wallet_dashboard'))                                                                                                                   
        return render_template('wallet/wallet_activate.html', account=account, action='verify')                                                                                   
    except Exception as e:                                                                                                                                                        
        current_app.logger.error(f"Wallet activation error: {e}")                                                                                                                 
        flash('Error loading wallet activation page', 'error')                                                                                                                    
        return redirect(url_for('wallet.wallet_dashboard'))                                                                                                                       
                                                                                                                                                                                  

Issue 7: Wallet Activation Template References wallet Variable                                                                                                                    

Location: templates/wallet/wallet_activate.html - line ~80                                                                                                                        

Description: The activation template references {{ wallet.id }}, {{ wallet.currency }}, and {{ wallet.created_at }} but the route passes account as the variable name, not wallet.
This will cause template rendering errors.                                                                                                                                        

Planned Fix:                                                                                                                                                                      

                                                                                                                                                                                  
# Option 1: Pass as 'wallet' instead of 'account'                                                                                                                                 
return render_template('wallet/wallet_activate.html', wallet=account, action='verify')                                                                                            
                                                                                                                                                                                  
# Option 2: Update template to use 'account' instead of 'wallet'                                                                                                                  
# Change {{ wallet.id }} to {{ account.id }}                                                                                                                                      
# Change {{ wallet.currency }} to {{ account.currency }}                                                                                                                          
# Change {{ wallet.created_at }} to {{ account.created_at }}                                                                                                                      
                                                                                                                                                                                  

Issue 8: Wallet Activation Template Form Missing CSRF Token                                                                                                                       

Location: templates/wallet/wallet_activate.html - activation form                                                                                                                 

Description: The activation form in the {% if action == 'verify' %} section uses <input type="hidden" name="csrf_token" value="{{ csrf_token }}"> but csrf_token is a callable    
function, not a string. This will render as <input value="<function ...>"> instead of the actual token.                                                                           

Planned Fix:                                                                                                                                                                      

                                                                                                                                                                                  
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">                                                                                                                
                                                                                                                                                                                  

Issue 9: Wallet Activation Template Form Missing accept_terms Field                                                                                                               

Location: templates/wallet/wallet_activate.html - activation form                                                                                                                 

Description: The activation form does not include a checkbox for accepting terms. The route wallet_activate_submit() checks request.form.get('accept_terms') but the form doesn't 
have this field. This means activation will always fail with "You must accept the terms to activate your wallet".                                                                 

Planned Fix:                                                                                                                                                                      

                                                                                                                                                                                  
<form method="POST">                                                                                                                                                              
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">                                                                                                              
  <input type="hidden" name="action_type" value="activate">                                                                                                                       
                                                                                                                                                                                  
  <div class="alert alert-warning" style="margin-bottom:20px;">                                                                                                                   
    <i class="fas fa-triangle-exclamation"></i>                                                                                                                                   
    By activating your wallet, you agree to our                                                                                                                                   
    <a href="{{ url_for('wallet.terms') }}" style="color:var(--accent-dk);font-weight:600;text-decoration:underline;">Wallet Terms and Conditions</a>.                            
  </div>                                                                                                                                                                          
                                                                                                                                                                                  
  <label style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer;margin-bottom:16px;">                                                                       
    <input type="checkbox" name="accept_terms" value="1" required>                                                                                                                
    I have read and accept the Terms and Conditions                                                                                                                               
  </label>                                                                                                                                                                        
                                                                                                                                                                                  
  <button type="submit" class="btn btn-success" style="width:100%;">                                                                                                              
    <i class="fas fa-check-circle"></i> Activate Wallet                                                                                                                           
  </button>                                                                                                                                                                       
</form>                                                                                                                                                                           
                                                                                                                                                                                  

----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------


14. Implementation Status Summary                                                                                                                                                 

                                                                                                               
 Component                                  Status          Notes                                              
 ───────────────────────────────────────────────────────────────────────────────────────────────────────────── 
 AccountModel with verified column          ✅ Complete     app/wallet/models/ledger.py                        
 get_or_create_account function             ✅ Complete     app/wallet/routes.py                               
 Wallet creation POST route                 ✅ Complete     app/wallet/routes.py                               
 Wallet activation POST route               ✅ Complete     app/wallet/routes.py                               
 WalletStatusService uses account.verified  ✅ Complete     app/wallet/services/wallet_status_service.py       
 Dynamic sidebar with feature gating        ✅ Complete     templates/wallet/base_wallet.html                  
 Wallet creation template                   ✅ Complete     templates/wallet/wallet_create.html                
 Wallet activation template                 ⚠️ Needs fixes  templates/wallet/wallet_activate.html (Issues 6-9) 
 Middleware decorators                      ✅ Complete     app/wallet/middleware/wallet_check.py              
 Context processor                          ✅ Complete     app/__init__.py                                    
 CSRF validation on activation              ❌ Missing      Issue 1                                            
 Re-activation prevention                   ❌ Missing      Issue 2                                            
 requires_terms_acceptance usage            ❌ Missing      Issue 3                                            
 require_payout_access consistency          ⚠️ Minor        Issue 4                                            
 redirect_to parameter usage                ⚠️ Minor        Issue 5                                            
 Activation template action variable        ❌ Missing      Issue 6                                            
 Activation template wallet variable        ❌ Missing      Issue 7                                            
 Activation template CSRF token             ❌ Missing      Issue 8                                            
 Activation template terms checkbox         ❌ Missing      Issue 9                                            
                                                                                                               

----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

Document generated: 2026-05-03 System version: AFCON360 Wallet v1.0                                                                                                               

▌ ▌ ▌ ▌ ▌ ▌ ▌ REPLACE                                                                                                                                                           

                                                                                                                                                                                  
                                      