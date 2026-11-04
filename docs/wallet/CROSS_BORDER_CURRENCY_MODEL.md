# AFCON360 Cross-Border Currency Model

**Status:** Product/architecture decision; implementation is staged.  
**Scope:** Wallet, Transport, Accommodation, Tourism, Events and any marketplace service that collects money for a provider.  
**Non-goal:** This document does not authorize live FX execution, local payment collection, or provider payouts by itself.

## 1. Product outcome

A customer can travel to another country and transact without learning that country's currency or calculating FX.

Example:

- Customer's regulated Wallet home currency: UGX.
- Customer books a service in Nigeria.
- Nigerian provider's invoice and local collection/settlement currency: NGN.
- Customer sees the price, authorization amount, Wallet debit and transaction history in UGX.
- Provider's payable/settlement remains NGN.
- Wallet records both sides of the conversion and the exact FX quote used.

The customer stays in their familiar currency; the provider operates and settles in the service market's currency.

## 2. Currency roles (do not conflate)

| Currency role | Authority | Purpose |
|---|---|---|
| Platform reference currency | Owner/platform pricing policy (USD may remain the reference) | Common pricing/reporting basis; not automatically the charge currency |
| Service/charge currency | Server-resolved service market and provider's eligible settlement market | Provider invoice, local collection and local settlement |
| Customer Wallet home currency | Wallet creation and applicable jurisdiction/compliance policy | Customer balance, debit, primary display and transaction history |
| Provider operating currency | Declared and subsequently verified operating country/market | Driver/provider-facing local amounts and payout eligibility |

Nationality and device/browser locale are not currency authorities. A customer's Wallet home currency must not change just because the customer crosses a border. A provider's service currency must not be taken from the customer's Wallet.

## 3. Authority for market and currency

- For a local service, determine the service market from the service location/fulfilment point and the provider's registered, permitted market.
- For Transport, the pickup/service market is the initial market authority; cross-border routes require an explicit rule for the market that owns the service/collection.
- For accommodation, events and tours, use the registered service/provider market and the actual service location.
- The browser may request a display preference, but it must never dictate the invoice currency or provider settlement currency.
- Multi-country providers must select a valid market/settlement entity for each offer or service; nationality is never a fallback.

## 4. Quote and checkout contract

Before the customer confirms, Wallet must obtain an executable, unexpired FX quote when charge currency differs from Wallet home currency.

The signed quote must bind at least:

- service reference and provider/market identity;
- service amount and service/charge currency;
- payer amount and Wallet home currency;
- rate direction and exact rate;
- provider/source and provider quote/reference ID;
- fees, spread and any tax disclosed to the customer;
- rounding/minor-unit policy;
- quote creation time and expiry;
- idempotency key and quote version.

The UI presents the payer's home-currency amount as the primary price. It also provides legally required charge-currency and FX details in a clear details/receipt view. Do not make the customer do the conversion.

If both currencies are the same, no conversion is needed. If the executable quote is missing, stale or expired, do not silently substitute a public indicative rate or mock rate. Re-quote before confirmation.

## 5. Invoice, payment and ledger contract

The marketplace invoice's amount/currency describe the provider's obligation in the service/charge currency. The same immutable invoice must retain the customer's home-currency debit amount and locked FX snapshot.

A cross-currency Wallet payment is not a same-currency transfer. Wallet must create linked, balanced per-currency accounting legs using controlled FX clearing/position accounts and an approved liquidity provider. The postings must reconcile to:

1. the customer's Wallet debit in home currency;
2. the FX provider's source and destination currency amounts;
3. the service-market collection/escrow amount in charge currency;
4. the provider's payable and eventual local-currency settlement.

Each currency's ledger must balance. A single ledger entry must never add UGX to NGN or pretend they are interchangeable. Transport must call Wallet's marketplace/FX boundary; it must not move funds or invent its own ledger entries.

Provider collection, payout, callbacks, refunds, reversals, idempotency, reconciliation and settlement failures belong to Wallet/payment orchestration.

## 6. Display rules

- Customer: show the Wallet home currency across search, price cards, review, confirmation, receipt, Wallet activity and transaction history.
- Provider/driver: show the currency of their verified operating/settlement market. Do not infer a driver's operating country from nationality or Wallet home currency.
- Owner/admin: show market currency and reference currency separately in pricing/financial reporting.
- Every converted amount must be traceable to its quote snapshot. An indicative estimate must not be described as a confirmed charge or Wallet debit.

## 7. Cash exception

Cash is physical. A customer in Nigeria who pays a Nigerian driver in cash must hand over NGN notes. The app can show the UGX equivalent and the exact NGN cash obligation, but software cannot make physical cash become UGX. The driver must confirm actual NGN receipt; Wallet must record cash receipt distinctly from a digital ledger payment.

## 8. FX provider and safety

The existing legacy Wallet FX service contains hard-coded mock rates with random variation and an api_live label. It is not an executable FX source and must not be used for real transactions.

The newer display FX adapter is an indicative presentation feed only. It is not sufficient for a Wallet debit, payment authorization, provider collection or settlement.

Production execution requires an approved regulated/contracted FX or PSP partner with:
- supported source/destination currencies and jurisdictions;
- executable, timestamped, expiring rates;
- disclosed fees/spread and exact settlement amounts;
- actual liquidity and local settlement capabilities;
- provider quote IDs and reliable confirmation/callbacks;
- refunds/reversals and reconciliation support;
- reviewed compliance, safeguarding and operational controls.

Until that partner and market/payment configuration are approved, fail closed on cross-currency Wallet settlement.

## 9. Refund and reversal policy

Every refund must reference the original invoice, payment attempt, FX quote and ledger postings. The product must define who bears FX movement/fees and whether a full refund returns the original home-currency debit or converts the original local-currency obligation at the refund-time rate. Do not silently calculate a new rate or create a cash refund through a non-cash payment rail.

## 10. Implementation sequence

1. Define supported home currencies by Wallet jurisdiction and supported service/settlement currencies by market.
2. Define provider/service-market resolution and Owner pricing: per-market pricebooks, or USD reference pricing converted under a reviewed local-price policy.
3. Select and integrate the executable FX/PSP partner.
4. Extend Wallet's immutable quote/invoice and payment-attempt contract to retain both currencies and the locked rate.
5. Implement per-currency clearing/ledger postings, provider local settlement, refunds and reconciliation.
6. Integrate each marketplace service through Wallet; add end-to-end tests for UGX Wallet → NGN provider, plus UGX/KES/TZS markets.
7. Enable each local payment method only after provider initiation, verification, callback, settlement and failure paths are tested.

## 11. Current implementation boundary

The Wallet home-currency and Transport display work in Draft PR #19 is a foundation only. It currently adds Wallet home-currency resolution, indicative display conversion, and driver operating-country declaration. The active Transport fare table still has one currency (USD); the invoice/settlement path still requires payer Wallet currency to match invoice currency; local Nigeria mobile-money marketplace methods are not enabled. The Uganda-to-Nigeria scenario is therefore **not yet executable end-to-end**.

No production database, server, active fare values or migrations are changed by the foundation PR.
