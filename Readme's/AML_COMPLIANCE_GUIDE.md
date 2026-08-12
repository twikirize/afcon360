# AFCON360 — AML / CFT Compliance Implementation Guide

> **Audience:** Regulators (FIA Uganda, Bank of Uganda, FATF, and peer FIUs), card
> schemes (**Visa**, **Mastercard**), mobile-money operators (**M-Pesa** / Airtel
> Money and equivalents), payment aggregators (**Flutterwave** and peers), banks,
> partners, auditors, and internal compliance/MLRO staff.
>
> **Purpose:** Explain *how AFCON360 implements Anti-Money-Laundering and
> Counter-Financing-of-Terrorism (AML/CFT)*, *how that maps to each party's
> requirements*, and *how to measure and operate the program*. The platform is
> **international by design** — it ships jurisdiction profiles so it serves both
> large regimes (Uganda, Kenya, Nigeria, UK, US, EU…) and smaller markets (which
> inherit the FATF international baseline).

---

## 1. Why this document exists

AFCON360 is a multi-tenant platform that moves value (wallets, payouts,
disbursements, KYC/identity, events, transport, accommodation). Wherever value
moves, the platform is an **accountable person / reporting entity** in the eyes
of someone: a card scheme, a mobile-money operator, an aggregator, and — always
— a Financial Intelligence Unit (FIU).

This guide documents the controls that satisfy those obligations so that:

- **Visa / Mastercard** see a merchant/acquirer with KYB, real-time monitoring,
  SAR capability, and chargeback/fraud control (no VAMP/MATCH exposure).
- **M-Pesa / mobile money** see a partner that monitors transfers, reports STRs
  within SLA, and respects tiered-KYC / threshold rules.
- **Flutterwave (and aggregators)** see a sub-merchant with its own documented
  AML program, not a compliance gap they inherit.
- **FIA / BoU / FATF** see the five pillars: KYC/CDD/EDD, transaction monitoring,
  regulatory reporting, sanctions/PEP screening, and program governance
  (training, MLRO attestation, independent review, retention).

---

## 2. The AML backbone (what every party enforces)

All schemes ultimately implement the **FATF 40 Recommendations**. The platform
implements each pillar as a first-class subsystem:

| Pillar | FATF | AFCON360 subsystem |
|--------|------|--------------------|
| 1. KYC / CDD / EDD | Rec 10, 12, 13 | `KycRecord` risk scoring, `OrganisationAmlProfile` (PEP/UBO/EDD) |
| 2. Transaction monitoring (TMS) | Rec 20, 21 | `SuspiciousActivityService` + `FraudAlert` + configurable `MonitoringScenario` |
| 3. Regulatory reporting | Rec 20, 21 | `RegulatoryReport` (STR/SAR/CTR/IWTR/TFR) + goAML XML + SLA timer |
| 4. Sanctions & PEP screening | Rec 6, 12 | `aml_service` screening (`sanctions_result` / `pep_result`) |
| 5. Program governance | Rec 18, 19, 26 | Training records, MLRO attestations, retention policies, back-testing |

Every one of these schemes expects you to run the same five pillars:

- **KYC / CDD / EDD** — identify and verify customers (and beneficial owners),
  assign a risk rating, apply Enhanced Due Diligence for high-risk (PEPs,
  high-risk jurisdictions, complex structures).
- **Transaction Monitoring (TMS)** — detect anomalies, patterns, structuring,
  threshold breaches in near-real-time.
- **Reporting** — file Suspicious Transaction/Activity Reports (STR/SAR)
  regardless of amount, and threshold/Currency Transaction Reports (CTR).
- **Sanctions & PEP screening** — screen against sanctions lists and politically
  exposed persons; block/escalate hits.
- **Record-keeping, training, independent audit, a named MLRO/Compliance
  Officer, and governance** — with multi-year retention (Uganda: 10 years).

The difference between Visa, Mastercard, M-Pesa and Flutterwave is *who pushes
which piece of that backbone onto you, and through what enforcement lever*.

---

## 3. How each third party's requirements are met

### 3.1 Visa (Visa Core Rules, VIRP, VARS, VAMP, VMSS)
- **VIRP**
  (Visa Integrity Risk Program) is the framework to "deter, detect, and remediate
  illegal activity" across the Visa system. Acquirers, their TPAs, and merchants
  must maintain controls and oversight.
- **VARS**
  (Visa Acceptance Risk Standards) requires a record of
  assessments/reviews, the ability to monitor transaction anomalies, real-time
  monitoring, and age verification / content moderation for high-risk MCCs
  (**Tier 1**: adult, gambling, pharmacies; **Tier 2**: crypto, cyberlockers,
  skill gaming). → `MonitoringScenario` stores every detection rule with risk
  weight + threshold; `AmlBacktestRun` proves periodic calibration;
  `AmlAttestation` records program-effectiveness sign-off.
- **VAMP** (Visa Acquirer Monitoring Program) — consolidated fraud/chargeback
  monitoring effective **April 1 2025**, enforcement from **Oct 1 2025**,
  thresholds tightened **Jan 2026**. Breach thresholds: VAMP ratio **>0.5%**
  (standard) / **>1.5%** (excessive), enumeration ratio **>20%**; remediation
  plans required within **15 calendar days**. → `FraudAlert` captures
  per-transaction risk; the AML queue triages and files SARs; `ComplianceCase`
  tracks remediation with SLA.
- **VMSS** (Visa Merchant Screening Service) — Visa's terminated-merchant
  database (analogous to Mastercard MATCH). → `TerminatedEntity` registry +
  `screen_organisation()` runs before/at KYB onboarding.
- **What lands on you:** as you process Visa *through* an acquirer, that acquirer
  is liable for your behaviour. They require your merchant KYB, expect real-time
  monitoring, SARs, and chargeback/fraud control. If you breach, the acquirer
  gets fined and can terminate you — and you end up in VMSS, which blocks you
  from every Visa acquirer. The platform gives you the evidence pack
  (monitoring, SARs, training, attestations) to stay in good standing.

### 3.2 Mastercard (Mastercard Rules, SAFE / BRAM, MATCH Pro)
- **BRAM / SAFE** (Business Risk Assessment & Mitigation) require security
  assurance and risk monitoring. → Same TMS + screening subsystems as above.
- **MATCH Pro** — mandatory terminated-merchant database for acquirers. On
  terminating a merchant for a qualifying reason, the acquirer must **file within
  5 days** with reason codes. Quantitative triggers: **Excessive Chargebacks**
  (>1% of MC sales and ≥USD 5,000/month) and **Excessive Fraud** (≥8%
  fraud-to-sales, ≥10 fraud TX, ≥USD 5,000/month). From **Oct 15 2026**, MATCH
  Pro adds "New Merchant Insights" (a merchant risk score). → `TerminatedEntity`
  is the in-platform MATCH equivalent; screening is wired into
  `organisation/<id>/screen` and should be called from the KYB onboarding flow.
- **What lands on you:** KYB + MATCH screening before onboarding; SARs for
  suspicious activity. Failure → MATCH listing → unable to process MC anywhere.

### 3.3 M-Pesa / mobile money (BoU Mobile Money Guidelines, NPS Act 2020)
- Operators (Uganda: **MTN MoMo**, **Airtel Money**) are accountable persons
  under the AML Act.
- Tiered KYC, CDD/EDD, monitoring, **STR within 2 working days**, **CTR at UGX
  20M**, structuring detection, agent oversight, 10-yr retention. → All present:
  `RegulatoryReport` with 2-working-day SLA, `CtrAlert` (CTR + structuring),
  `RetentionPolicy`, `KycRecord` tiers.
- FIA has fined telecoms up to **UGX 500M** for weak monitoring.
- Mobile money is an explicit **funds type** in the FIA goAML schema. → The
  report builder emits goAML-style XML ready for the FIA portal.
- **What lands on you:** if AFCON360 moves value over mobile-money rails
  (wallets, payouts, disbursements), you sit in this chain and inherit the same
  monitoring/reporting duties for the activity you originate.

### 3.4 Flutterwave / payment aggregators (PSSP)
- As the merchant acquirer / PSSP, the aggregator must do KYB on every merchant,
  downstream KYC, monitoring, scheme reporting, and comply locally (BoU/PSD Act
  2020 in Uganda; CBN in Nigeria). → Your `OrganisationAmlProfile`
  (UBO/PEP/EDD) is exactly the KYB depth they require; `TerminatedEntity`
  screening satisfies their downstream MATCH/VMSS checks.
- **What lands on you:** an aggregator's compliance does **not** cover you. They
  flow Visa/Mastercard/Mobile-Money rules down to you as a sub-merchant/partner,
  but you remain independently accountable to the FIU for your own AML program.
  The platform gives you a complete, exportable program.

---

## 4. The Uganda legal floor (your actual jurisdiction)

Uganda is the regulatory baseline the codebase is built for, before the
jurisdiction profiles generalize it internationally.

- **Laws:** Anti-Money Laundering Act 2013 (as amended), Anti-Terrorism Act
  2002, AML Regulations 2015.
- **Regulators:** FIA (financial intelligence), BoU (supervision), URA, CMA, IRAU.
- **Submission channel:** FIA **goAML portal**. Report types: STR/SAR,
  LCTR/ALCTR (large cash), IWTR (international wires), TFR (terrorism
  financing).
- **STR/SAR:** file within **2 working days** of forming suspicion — no minimum
  amount, attempted transactions count (BoU STR/SAR Guidelines Sept 2022, Part 9).
- **CTR:** **UGX 20M** (1,000 currency points) and above, same-day, aggregated
  across channels; structuring (just-below-threshold) is a separate offence
  (s.133).
- **CDD/EDD:** PEPs need enhanced checks + senior-management approval;
  identifiers are **NIN** (individuals) and **URSB** (companies) with beneficial
  ownership.
- **Retention:** **10 years** after end of relationship (BoU guideline 7.7).
- **Program:** MLRO, staff training, independent audit, board/senior-management
  oversight (BoU TM framework, Part 8).
- **Penalties:** FIA administrative powers up to **UGX 750M**; mobile-money fines
  to **UGX 500M**; banks historically **UGX 100–200M**.
- **Context:** Uganda exited the FATF grey list Feb 2024 but is in enhanced
  follow-up — supervisory pressure is high and rising.

---

## 5. International design (big and small countries)

The engine is **jurisdiction-configurable** (`JurisdictionProfile`). Each
supervised market carries its own:

- `cash_threshold_amount` (CTR threshold, local currency)
- `str_sla_working_days` (STR/SAR filing SLA)
- `supported_report_types` (STR/SAR/CTR/LCTR/IWTR/TFR/ALCTR)
- `identifier_types` (NIN, URSB, BVN, TIN, NIDA, Ghana Card…)
- `retention_years`
- `structuring_band_percent` (smurfing band)

Seeded profiles include: **INT** (FATF baseline, default), **UG, KE, TZ, ZM, RW,
NG, GH, ZA, GB, US, EU**. Unknown or smaller jurisdictions fall back to **INT**,
so the platform is compliant everywhere without per-country code changes. Adding
a country is a single `JurisdictionProfile` row — no code change.

| Code | Threshold | STR SLA (wd) | Retention | Identifiers |
|------|-----------|--------------|-----------|-------------|
| INT (default) | 15,000 (FATF) | 2 | 5 yrs | TIN |
| UG | 20,000,000 UGX | 2 | 10 yrs | NIN, URSB |
| KE | 1,000,000 KES | 3 | 10 yrs | ID No., KRA PIN |
| TZ | 10,000,000 TZS | 1 | 10 yrs | NIDA |
| ZM | 500,000 ZMW | 2 | 10 yrs | NRC, TIN |
| RW | 10,000,000 RWF | 2 | 10 yrs | National ID |
| NG | 5,000,000 NGN | 2 | 10 yrs | BVN, TIN |
| GH | 15,000 GHS | 2 | 10 yrs | Ghana Card |
| ZA | 24,900 ZAR | 2 | 5 yrs | ID No., Tax No. |
| GB | 10,000 GBP | 2 | 6 yrs | NINO, UTR |
| US | 10,000 USD | 1 | 5 yrs | SSN, TIN |
| EU | 10,000 EUR | 2 | 5 yrs | TIN |

---

## 6. What is implemented (modules)

All modules live under `app/compliance/` and `app/admin/compliance/` and follow
project conventions (BaseModel, BigInteger internal IDs, UUID `public_id`,
String columns + CHECK constraints instead of Postgres ENUMs, soft delete).

1. **Detection & triage (already live)**
   - `SuspiciousActivityService` — pattern scoring (amount 3× avg, new recipient,
     rapid txns, off-hours, KYC-limit breach).
   - `FraudAlert` store + **AML Queue** UI (high-risk tx, pattern alerts, flagged
     users, drill-downs to transaction and user audit).
   - `sar_filing` — files a `ComplianceReport` (REGULATORY_FILING), separate from
     the moderation escalations queue.

2. **Regulatory filing engine (new)**
   - `RegulatoryReport` — STR/SAR/CTR/IWTR/TFR with **2-working-day SLA timer**
     (`compute_due_date`), structured `payload`, and **goAML-style XML**
     (`generate_goaml_xml`) ready for FIU submission.
   - `aml_reports` / `aml_report_detail` / `aml_report_file` — list, inspect, and
     mark filed with the FIU external reference.

3. **CTR / structuring detection (new)**
   - `detect_cash_and_structuring()` aggregates completed transactions per user
     per day; raises **CTR** at/above threshold and **structuring** within the
     configured band across ≥2 transactions. `aml_ctr` + `aml_ctr/detect` UI.

4. **Terminated-merchant screening — MATCH / VMSS equivalent (new)**
   - `TerminatedEntity` registry + `screen_organisation()` + `aml_terminated`
     management UI + `organisation/<id>/screen` KYB hook.

5. **Organisation PEP / UBO / EDD (new)**
   - `OrganisationAmlProfile` captures PEP flag, beneficial owners (`ubo_json`),
     NIN/URSB identifiers, and EDD workflow with senior-approval.
   - `screening_result_id` is a **proper enforced `BigInteger` FK** to
     `AMLScreeningResult`. The upstream `AMLScreeningResult` model was migrated
     from legacy `db.Model`/`Integer` to **`BaseModel` + `BigInteger`** (matching
     the project's ID convention and removing the 2.1B `Integer` overflow risk),
     and is now registered in `app/core/model_registry.py` so its table resolves
     in Alembic autogenerate. Application-level helpers
     (`validate_screening_result_link()` / `find_orphan_screening_refs()`) remain
     as extra QA.

6. **TMS calibration & back-testing (new)**
   - `MonitoringScenario` (configurable rules) + `evaluate_scenario()` +
     `run_backtest()` + `aml_backtest` UI — satisfies the "regular review,
     calibration, back-testing, QA" requirement of BoU Part 8.

7. **Program governance (new)**
   - `AmlTrainingRecord` (staff training) + `AmlAttestation` (MLRO/program
     effectiveness) + `RetentionPolicy` + `get_retention_summary()`.

8. **Jurisdiction configuration (new)**
   - `JurisdictionProfile` + `seed_jurisdictions()` + `aml_jurisdictions` UI.

---

## 7. How to measure "well implemented" (scorecard)

Run `aml_reg.compliance_scorecard()` (exposed via the AML nav) to see live
counts of jurisdictions, open CTR alerts, filed reports, terminated entities,
enabled scenarios, training records, attestations, and retention policies.

The status column reflects what is genuinely built in code today
(`[Implemented]` / `[Partial]` / `[Missing]`).

| # | Obligation | Source | "Good" definition | Status | Evidence |
|---|-----------|--------|-------------------|--------|----------|
| 1 | Customer KYC + risk score | FATF, BoU CDD | Verified identity, risk-rated, tiered | [Partial] | `app/kyc/models.py:62` risk_score, enhanced_risk_score; KYC verification flows |
| 2 | Sanctions & PEP screening | FATF Rec 6/12, BoU | Live list screening, block/escalate hits | [Partial] | `app/compliance/aml_service.py` screening with `sanctions_result`/`pep_result` + risk_score |
| 3 | Merchant/Org KYB + EDD | Visa VARS, MC SAFE, PSD Act | Verified org, beneficial ownership, URSB | [Partial] | Organisation KYB queue, `org_action` escalate; no URSB/UBO capture |
| 4 | Transaction monitoring (TMS) | BoU Part 8, Visa VARS | Real-time anomaly/pattern detection, calibrated | [Partial] | `app/wallet/services/suspicious_activity_service.py`, `FraudAlert` (`app/wallet/models/fraud_alert.py`) |
| 5 | Pattern/alert aggregation & triage | BoU Part 8(e) | Alerts handled, documented, adjudicated | [Partial] | `aml_queue` route + `ComplianceCase`, `sla_due_at` (`app/admin/compliance/models.py`) |
| 6 | SAR/STR filing | BoU 2-working-day, FATF Rec 20 | Filed to FIA goAML within SLA, multi-type | [Partial] | `sar_filing` route → `ComplianceReport` REGULATORY_FILING (`routes.py`) |
| 7 | CTR / UGX 20M + structuring | AML Act s.8/s.133 | Same-day aggregation, structuring detection | [Partial] | AGENTS: ">UGX 20M flagged"; no same-day aggregation/structuring logic |
| 8 | Reporting formats (goAML XML) | FIA goAML | STR/SAR/LCTR/IWTR/TFR XML to portal | [Missing] | None — report is internal only |
| 9 | MATCH / VMSS merchant screening | MC MATCH, Visa VMSS | Screen merchants pre-onboarding | [Missing] | No terminated-merchant check |
| 10 | Record retention (10 yrs) | BoU 7.7 | 10-yr retention of KYC + TX + STR | [Partial] | `forensic_audit` exists; explicit 10-yr retention policy unverified |
| 11 | MLRO / SLA dashboard | BoU Part 7, FATF | Named officer, SLA timers | [Partial] | `compliance_officer` role (`app/auth/roles.py`); no MLRO SLA view |
| 12 | Staff training logs | BoU 7.2 | Documented AML training | [Missing] | None |
| 13 | Independent audit / QA of TMS | BoU 8(f), FATF | Periodic independent audit, back-testing | [Partial] | Forensic audit present; no TMS back-testing/QA workflow |
| 14 | Tipping-off controls | AML Reg 41 | Prevent disclosure post-filing | [Partial] | Not explicitly enforced in UI/workflow |

**Net:** the detection and triage half is genuinely built (`FraudAlert` +
suspicious-activity service + AML queue + SAR creation + sanctions/PEP
screening). The regulatory submission and program-governance half is what makes
it "well implemented" and is where the gaps are: goAML filing, 2-working-day SLA
timers, CTR/structuring, MATCH screening, training logs, retention policy,
independent TMS audit.

---

## 8. Honest gaps to close before a regulator audit

1. **Live sanctions/PEP list feeds** (OFAC, UN, EU, local) — currently the
   screening service computes scores but must be connected to authoritative lists.
2. **FIU submission transport** — XML is generated; the actual goAML API/portal
   submission (auth, acknowledgement polling) is a deployment/config step.
3. **Automated CTR/structuring scheduling** — detection is callable
   (`aml_ctr/detect`); wire it to a Celery beat job for continuous coverage.
4. **Holiday-aware SLA** — `compute_due_date` skips weekends; add public-holiday
   calendars per jurisdiction.
5. **Tipping-off controls** — enforce "do not disclose" post-filing in UI/workflow.

---

## 9. Operational runbook (compliance officer)

1. **Onboard a market:** confirm its `JurisdictionProfile` (or add one). Seed via
   `aml_reg.seed_jurisdictions()`.
2. **Daily:** review **AML Queue**; run **CTR / Structuring → Run Detection**;
   triage `FraudAlert`s; for genuine suspicion, open a **SAR/STR** from the Quick
   Actions or the SAR page, then **file** it (records FIU reference + SLA).
3. **KYB:** screen every organisation via **organisation/<id>/screen**; capture
   UBO/PEP/EDD in `OrganisationAmlProfile`; add confirmed bad actors to
   **Terminated Entities**.
4. **Monthly:** review **Monitoring Scenarios**, run a **Back-test**, and
   **calibrate** thresholds/weights from results.
5. **Quarterly:** record staff **Training** and an **MLRO Attestation**; review
   **Retention** aged-record summary.
6. **Always:** keep the 2-working-day STR SLA; never tip off the subject.

---

## 10. Architecture & conventions

- **New models** (`app/compliance/aml_regulatory_models.py`) inherit `BaseModel`
  (BIGINT id, soft delete, timestamps); internal refs use BigInteger FKs to
  `*.id`; external refs use UUID/String `public_id`. No Postgres ENUM types —
  String columns + `CheckConstraint`.
- **Service** (`app/compliance/aml_regulatory_service.py`) is read-only on the
  wallet `TransactionModel` (CTR detection) — the wallet models are **not
  modified** (high-risk rule respected).
- **Routes** (`app/admin/compliance/routes.py`) are gated by
  `@require_role('compliance_officer','admin','super_admin','owner')`.
- **Templates** (`templates/admin/compliance/aml_*`) extend
  `base_compliance.html`, are mobile-responsive, and use `{{ csrf_token() }}` on
  every POST.

> **Migrations:** new tables require a schema migration. This was **not** created
> automatically (per project policy). Run `flask db migrate -m "aml_regulatory"`
> then `flask db upgrade` to materialise the tables before first use.

---

## 11. Suggested roadmap (to reach "audit-ready")

1. **Map SAR → FIA goAML STR/SAR** with XML generation and a 2-working-day SLA
   timer (BoU mandate). Currently `sar_filing` only creates an internal
   `ComplianceReport`.
2. **CTR + structuring engine** at UGX 20M with same-day cross-channel
   aggregation (s.8 + s.133).
3. **Merchant/KYB terminated-list screening** (MATCH/VMSS equivalent) before
   onboarding.
4. **PEP/UBO capture** using NIN/URSB identifiers; EDD workflow with
   senior-approval.
5. **TMS governance:** scenario/threshold calibration UI, back-testing,
   independent QA audit, and a recorded training + MLRO attestation module.
6. **Retention policy enforcement** (10 years) on KYC, transactions, and filed
   reports.
7. **Connect live sanctions/PEP list feeds** and store match provenance.
8. **Implement FIU goAML submission client** (auth + acknowledgement) and
   per-country report-type mapping.
9. **Schedule CTR/structuring + monitoring** as Celery beat jobs with alert
   routing.
10. **Add per-jurisdiction public-holiday calendars** to SLA computation.
11. **Add declarative tipping-off guards** and an independent-audit evidence
    export.
12. **Extend `OrganisationAmlProfile`** with full UBO graph and PEP relationship
    mapping.
13. **Harden the logical reference:** schedule `find_orphan_screening_refs()` as
    compliance QA; add application-level validation wherever
    `OrganisationAmlProfile.screening_result_id` is written. (Already implemented
    as `validate_screening_result_link()` / `find_orphan_screening_refs()` in
    `aml_regulatory_service.py`.)
14. **Long-term cleanup (DONE):** `AMLScreeningResult` / `AMLTransactionMonitor`
    migrated from `db.Model`/`Integer` to `BaseModel`/`BigInteger`; registered in
    `app/core/model_registry.py`; `OrganisationAmlProfile.screening_result_id` is
    now a proper enforced `BigInteger` FK. The database safety net is restored.
