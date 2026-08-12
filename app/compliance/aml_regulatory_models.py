"""
AML Regulatory Models — jurisdiction-aware anti-money-laundering program.

These models implement the *regulatory submission and program-governance* half
of an AML/CFT system: jurisdiction profiles (so the platform can serve both
large and small jurisdictions), regulatory report filings (STR/SAR, CTR/LCTR,
IWTR, TFR) with SLA timers, large-cash / structuring detection, terminated
merchant screening (MATCH / VMSS equivalent), organisation PEP / UBO / EDD
profiles, transaction-monitoring scenario calibration and back-testing, staff
training, MLRO attestations, and retention policies.

Conventions (per AGENTS.md):
- Inherit from BaseModel (BIGINT id, soft delete, timestamps).
- Internal references use BigInteger FKs to `*.id`.
- External identifiers use UUID/String `public_id` and never raw `id`.
- No PostgreSQL ENUM types — String columns + CHECK constraints instead.
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Column, BigInteger, String, Boolean, DateTime, Text, Numeric,
    JSON, Date, Integer, Float, ForeignKey, CheckConstraint,
)
from app.extensions import db
from app.models.base import BaseModel


# ---------------------------------------------------------------------------
# Jurisdiction profiles — the internationalisation layer.
# Every supervised entity operates under one (or more) jurisdictions. Smaller
# countries inherit the FATF baseline; larger regimes (Uganda, Kenya, etc.)
# override thresholds, SLAs, report types and identifier schemes.
# ---------------------------------------------------------------------------
class JurisdictionProfile(BaseModel):
    __tablename__ = 'aml_jurisdiction_profiles'
    __table_args__ = (
        CheckConstraint(
            "str_sla_working_days >= 0 AND str_sla_working_days <= 30",
            name='ck_jurisdiction_sla_range'
        ),
        CheckConstraint(
            "retention_years >= 0 AND retention_years <= 50",
            name='ck_jurisdiction_retention_range'
        ),
    )

    country_code = Column(String(2), unique=True, nullable=False, index=True)
    country_name = Column(String(120), nullable=False)
    currency_code = Column(String(3), nullable=False)
    # Cash / large-transaction reporting threshold in local currency.
    cash_threshold_amount = Column(Numeric(18, 2), nullable=False, default=0)
    # Optional "currency points" style threshold (e.g. Uganda 1 point = UGX 20,000).
    currency_point_value = Column(Numeric(18, 2), nullable=True)
    cash_threshold_points = Column(Numeric(18, 2), nullable=True)
    # STR/SAR filing SLA measured in *working days* from suspicion formed.
    str_sla_working_days = Column(Integer, nullable=False, default=2)
    # Alert if aggregated activity sits within this % below the threshold
    # (structuring / smurfing detection band). 0 disables.
    structuring_band_percent = Column(Integer, nullable=False, default=10)
    # Supported goAML-style report types for this jurisdiction.
    supported_report_types = Column(JSON, nullable=False, default=list)
    # Identifier schemes expected for subjects (NIN, URSB, TIN, BVN, ...).
    identifier_types = Column(JSON, nullable=False, default=list)
    retention_years = Column(Integer, nullable=False, default=10)
    is_default = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    notes = Column(Text, nullable=True)


class RegulatoryReport(BaseModel):
    """A regulatory filing (STR/SAR, CTR/LCTR, IWTR, TFR) to a Financial Intelligence Unit."""
    __tablename__ = 'aml_regulatory_reports'
    __table_args__ = (
        CheckConstraint(
            "report_type IN ('str','sar','ctr','lctr','iwtr','tfr','alctr')",
            name='ck_regulatory_report_type'
        ),
        CheckConstraint(
            "status IN ('draft','submitted','accepted','rejected','filed')",
            name='ck_regulatory_report_status'
        ),
        CheckConstraint(
            "subject_type IN ('individual','organisation','transaction')",
            name='ck_regulatory_report_subject_type'
        ),
    )

    public_id = Column(String(36), unique=True, nullable=False, index=True)
    report_number = Column(String(50), unique=True, nullable=False, index=True)

    jurisdiction_id = Column(BigInteger, ForeignKey('aml_jurisdiction_profiles.id'), nullable=True, index=True)
    report_type = Column(String(20), nullable=False, index=True)
    status = Column(String(20), nullable=False, default='draft', index=True)

    subject_type = Column(String(20), nullable=False, default='individual')
    subject_user_id = Column(BigInteger, ForeignKey('users.id'), nullable=True, index=True)
    subject_org_id = Column(BigInteger, ForeignKey('organisations.id'), nullable=True, index=True)
    # Identifier used in the actual filing (NIN / URSB / TIN / public_id).
    subject_identifier = Column(String(120), nullable=True)
    subject_name = Column(String(255), nullable=True)
    related_transaction_id = Column(String(64), nullable=True, index=True)

    risk_score = Column(Float, nullable=True)
    narrative = Column(Text, nullable=True)
    amount = Column(Numeric(18, 2), nullable=True)
    currency_code = Column(String(3), nullable=True)

    suspicion_formed_at = Column(DateTime, nullable=True)
    due_at = Column(DateTime, nullable=True, index=True)
    filed_at = Column(DateTime, nullable=True)
    filed_by = Column(BigInteger, ForeignKey('users.id'), nullable=True)
    external_reference = Column(String(120), nullable=True)

    # Full goAML-style structured payload + generated XML for submission.
    payload = Column(JSON, nullable=True)
    xml_content = Column(Text, nullable=True)


class CtrAlert(BaseModel):
    """Large-cash (CTR) or structuring alert surfaced by the detection engine."""
    __tablename__ = 'aml_ctr_alerts'
    __table_args__ = (
        CheckConstraint(
            "alert_type IN ('ctr','structuring')",
            name='ck_ctr_alert_type'
        ),
        CheckConstraint(
            "status IN ('open','reported','dismissed')",
            name='ck_ctr_alert_status'
        ),
    )

    public_id = Column(String(36), unique=True, nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey('users.id'), nullable=True, index=True)
    jurisdiction_id = Column(BigInteger, ForeignKey('aml_jurisdiction_profiles.id'), nullable=True, index=True)
    alert_type = Column(String(20), nullable=False, index=True)
    period_date = Column(Date, nullable=False, index=True)
    aggregated_amount = Column(Numeric(18, 2), nullable=False, default=0)
    transaction_count = Column(Integer, nullable=False, default=0)
    threshold_amount = Column(Numeric(18, 2), nullable=True)
    status = Column(String(20), nullable=False, default='open', index=True)
    reported_report_id = Column(BigInteger, ForeignKey('aml_regulatory_reports.id'), nullable=True)
    details = Column(JSON, nullable=True)


class TerminatedEntity(BaseModel):
    """Registry of terminated / high-risk merchants and individuals (MATCH / VMSS equivalent)."""
    __tablename__ = 'aml_terminated_entities'
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('organisation','individual')",
            name='ck_terminated_entity_type'
        ),
        CheckConstraint(
            "source IN ('match','vmss','internal','manual','regulator')",
            name='ck_terminated_entity_source'
        ),
    )

    public_id = Column(String(36), unique=True, nullable=False, index=True)
    entity_type = Column(String(20), nullable=False, default='organisation')
    name = Column(String(255), nullable=False)
    registration_number = Column(String(120), nullable=True, index=True)
    national_id = Column(String(120), nullable=True, index=True)
    source = Column(String(50), nullable=False, default='manual')
    reason_code = Column(String(40), nullable=True)
    reason_text = Column(Text, nullable=True)
    terminated_at = Column(DateTime, nullable=True)
    added_by = Column(BigInteger, ForeignKey('users.id'), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)


class OrganisationAmlProfile(BaseModel):
    """PEP / beneficial-ownership / EDD profile for an organisation (KYB depth)."""
    __tablename__ = 'aml_organisation_profiles'
    __table_args__ = (
        CheckConstraint(
            "edd_status IN ('not_required','required','in_progress','completed')",
            name='ck_org_aml_edd_status'
        ),
    )

    public_id = Column(String(36), unique=True, nullable=False, index=True)
    organisation_id = Column(BigInteger, ForeignKey('organisations.id'), nullable=False, unique=True, index=True)
    is_pep = Column(Boolean, default=False, nullable=False)
    pep_details = Column(JSON, nullable=True)
    ubo_json = Column(JSON, nullable=True)  # list of beneficial owners
    nin = Column(String(120), nullable=True)            # individual NIN (sole prop)
    ursb_registration = Column(String(120), nullable=True)  # URSB / company reg
    edd_status = Column(String(20), nullable=False, default='not_required')
    edd_rationale = Column(Text, nullable=True)
    edd_approved_by = Column(BigInteger, ForeignKey('users.id'), nullable=True)
    edd_approved_at = Column(DateTime, nullable=True)
    # Proper enforced FK to the AML screening result. AMLScreeningResult now
    # inherits BaseModel with a BigInteger PK (see app/compliance/aml_service.py),
    # so the types align and the reference is database-enforced. Application-level
    # helpers (validate_screening_result_link / find_orphan_screening_refs) remain
    # as extra QA.
    screening_result_id = Column(BigInteger, ForeignKey('aml_screening_results.id'), nullable=True, index=True)


class MonitoringScenario(BaseModel):
    """A configurable transaction-monitoring rule (TMS calibration unit)."""
    __tablename__ = 'aml_monitoring_scenarios'
    __table_args__ = (
        CheckConstraint(
            "category IN ('amount','velocity','pattern','geography','sanctions','pep')",
            name='ck_monitoring_scenario_category'
        ),
    )

    public_id = Column(String(36), unique=True, nullable=False, index=True)
    name = Column(String(120), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(40), nullable=False, default='pattern')
    risk_weight = Column(Integer, nullable=False, default=0)
    threshold_value = Column(Numeric(18, 4), nullable=True)
    is_enabled = Column(Boolean, default=True, nullable=False)
    parameters = Column(JSON, nullable=True)
    last_calibrated_at = Column(DateTime, nullable=True)
    last_calibrated_by = Column(BigInteger, ForeignKey('users.id'), nullable=True)


class AmlBacktestRun(BaseModel):
    """Record of a transaction-monitoring scenario back-test."""
    __tablename__ = 'aml_backtest_runs'

    public_id = Column(String(36), unique=True, nullable=False, index=True)
    scenario_id = Column(BigInteger, ForeignKey('aml_monitoring_scenarios.id'), nullable=True, index=True)
    run_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    window_start = Column(DateTime, nullable=True)
    window_end = Column(DateTime, nullable=True)
    transactions_scored = Column(Integer, nullable=False, default=0)
    alerts_generated = Column(Integer, nullable=False, default=0)
    true_positives = Column(Integer, nullable=True)
    false_positives = Column(Integer, nullable=True)
    precision_score = Column(Float, nullable=True)
    recall_score = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)


class AmlTrainingRecord(BaseModel):
    """Staff AML/CFT training completion record."""
    __tablename__ = 'aml_training_records'

    public_id = Column(String(36), unique=True, nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey('users.id'), nullable=False, index=True)
    training_module = Column(String(120), nullable=False)
    completed_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    score = Column(Integer, nullable=True)
    certificate_ref = Column(String(120), nullable=True)
    expires_at = Column(DateTime, nullable=True)
    delivered_by = Column(String(120), nullable=True)


class AmlAttestation(BaseModel):
    """MLRO / compliance officer attestation of program effectiveness."""
    __tablename__ = 'aml_attestations'
    __table_args__ = (
        CheckConstraint(
            "attestation_type IN ('mlro_quarterly','program_effectiveness','tms_review')",
            name='ck_aml_attestation_type'
        ),
        CheckConstraint(
            "status IN ('draft','submitted','archived')",
            name='ck_aml_attestation_status'
        ),
    )

    public_id = Column(String(36), unique=True, nullable=False, index=True)
    attestation_type = Column(String(40), nullable=False, default='mlro_quarterly')
    period_start = Column(DateTime, nullable=True)
    period_end = Column(DateTime, nullable=True)
    attested_by = Column(BigInteger, ForeignKey('users.id'), nullable=False, index=True)
    attested_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    statement = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default='submitted')
    document_ref = Column(String(120), nullable=True)


class RetentionPolicy(BaseModel):
    """Per-resource-type record retention policy (10-year baseline)."""
    __tablename__ = 'aml_retention_policies'
    __table_args__ = (
        CheckConstraint(
            "resource_type IN ('kyc','transaction','regulatory_report','aml_screening','audit_log')",
            name='ck_retention_resource_type'
        ),
    )

    public_id = Column(String(36), unique=True, nullable=False, index=True)
    resource_type = Column(String(60), nullable=False, unique=True)
    retention_years = Column(Integer, nullable=False, default=10)
    auto_purge = Column(Boolean, default=False, nullable=False)
    is_enabled = Column(Boolean, default=True, nullable=False)
    last_reviewed_at = Column(DateTime, nullable=True)
    reviewed_by = Column(BigInteger, ForeignKey('users.id'), nullable=True)
    notes = Column(Text, nullable=True)
