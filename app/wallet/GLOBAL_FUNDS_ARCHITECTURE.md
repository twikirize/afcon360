# AFCON360 Global Funds Architecture: Deposits & Transfers

**Status:** Proposed Architecture
**Scope:** Wallet Cash-In (Deposits) & Cash-Out/P2P (Transfers)
**Goal:** A legally compliant, multi-currency, pan-African wallet that requires zero "shadow banking" or excessive corporate banking footprints, optimized for cross-border usability.

---

## 1. Executive Summary (The Investor Pitch)

AFCON360 operates a **"Borderless Native Wallet"**. Every user holds a wallet in their verified Home Currency (e.g., a Nigerian holds NGN). However, they can deposit funds, pay merchants, or send money using **any currency in Africa**. 

We achieve this without opening 50+ corporate bank accounts or becoming an unregulated offshore bank. By combining our **Internal FX Engine** with **Pan-African Payment Aggregators (like Flutterwave/MFS Africa)**, the aggregator handles local cash collection and cross-border settlement, while our internal ledger updates user balances in real-time. 

**The result:** AFCON360 profits on automated FX spreads, maintains 100% regulatory compliance, and provides users with a magical, frictionless cross-border experience.

---

## 2. Activity 1: The Deposit System (Cash-In)

The deposit system is how funds enter the AFCON360 ecosystem. It is governed by strict KYC volume limits and AML (Anti-Money Laundering) checks.

### Scenario A: Home Currency Deposits (e.g., Nigerian in Nigeria)
When a user deposits using a method native to their wallet currency (e.g., NGN Wallet depositing via Paystack, MTN Nigeria, or an NGN Visa Card).
* **Flow:** User enters 10,000 NGN. The gateway processes 10,000 NGN. 
* **Ledger:** The system receives the webhook and instantly credits the wallet exactly 10,000 NGN.
* **FX:** None required.

### Scenario B: Cross-Border Gateway Deposits (e.g., Nigerian in Kenya)
When a user is traveling and needs to top-up their NGN wallet using local foreign funds (e.g., M-Pesa KES).
* **Step 1 (The Quote):** The user selects "M-Pesa (Kenya)". They enter 1,000 KES. Our Internal FX Engine (`fx.py`) fetches the real-time rate, applies a platform spread (profit margin), and tells the user: *"You will be credited 11,500 NGN."*
* **Step 2 (The Aggregator):** The user approves the M-Pesa push. The KES is collected into **Flutterwave's** Kenyan corporate bank account.
* **Step 3 (The Ledger Credit):** Flutterwave fires a webhook to AFCON360. We credit the user's wallet with 11,500 NGN. 
* **Step 4 (Settlement):** Flutterwave converts the KES internally and wires the equivalent NGN/USD to AFCON360's primary corporate account. 

### Scenario C: Agent Cash-In (Physical Cash)
When a user wants to hand physical cash to an authorized AFCON360 agent.
* **Step 1:** The user selects "Agent Cash-In" on the app and generates a secure **Pending Deposit Intent (Reference Code)**.
* **Step 2:** The user hands the cash and the code to the agent.
* **Step 3:** The agent logs into the Agent Portal, inputs the code, and confirms receipt of funds. The system deducts the agent's pre-funded digital float and credits the user's wallet.

### Compliance & Regulatory Guards
* **KYC Tiers:** `KYCLimitService` actively intercepts every deposit. If an unverified user tries to deposit large sums, the transaction is hard-blocked.
* **Source of Funds (AMLD6):** Deposits above high-risk thresholds (e.g., >$10k equivalent) dynamically trigger a mandatory "Source of Wealth" declaration form before the gateway is initialized.

---

## 3. Activity 2: Transfers & Sending (Cash-Out)

Money movement out of a wallet happens in two ways: internal wallet-to-wallet transfers (P2P), or external sending (Cash-Out/Remittance).

### Scenario A: Internal Wallet-to-Wallet (P2P)
Sending money to another AFCON360 user globally. This is the cheapest and fastest transaction because money never leaves our database.

* **Same Currency (NGN to NGN):** 
  * Sender debited 10,000 NGN. Receiver credited 10,000 NGN. Free and instant.
* **Cross-Currency (Nigerian NGN to Kenyan KES wallet):** 
  * The Nigerian sender wants to send 5,000 KES to their Kenyan friend.
  * Our `FXRateModel` calculates that 5,000 KES costs 57,500 NGN (including our spread).
  * **Ledger Action:** Sender's wallet is debited 57,500 NGN. Receiver's wallet is credited 5,000 KES. 
  * **Result:** No actual money moved across borders. We simply updated two rows in our database and collected the FX spread as revenue.

### Scenario B: External Sending / Withdrawals (Wallet to Bank/Mobile Money)
When a user wants to send funds from their AFCON360 wallet out to a traditional bank account or Mobile Money number.

* **Domestic Withdrawal (NGN Wallet to Nigerian Bank):**
  * User requests withdrawal of 50,000 NGN.
  * System debits 50,000 NGN from their wallet.
  * System triggers an API call to our payment aggregator (e.g., Flutterwave Transfers API) to push 50,000 NGN to the target bank account.
* **Cross-Border Remittance (NGN Wallet to Ugandan MTN Mobile Money):**
  * User wants to send 100,000 UGX to a family member in Uganda.
  * **FX Check:** System quotes the user the NGN cost (e.g., 40,000 NGN).
  * **Ledger Action:** System debits the user's wallet 40,000 NGN.
  * **Aggregator Action:** System triggers an API call to Flutterwave to deliver 100,000 UGX to the Ugandan phone number. Flutterwave handles the last-mile delivery and deducts the balance from AFCON360's corporate settlement account.

---

## 4. The Unified Technical Flow

Regardless of whether it is a Deposit or a Transfer, the technical stack relies on a unified flow:

1. **Gatekeeper:** Check `KYCLimitService` (Does the user have permission/limits for this volume?).
2. **FX Evaluator:** Check `FXRateModel` (Is this cross-currency? If yes, lock in a quoted rate and calculate spread).
3. **Execution:** Ping the Aggregator Gateway (Flutterwave, MTN, Paystack).
4. **Audit & Ledger:** Write immutably to `TransactionModel` and `LedgerModel` only upon definitive success/webhook confirmation.
