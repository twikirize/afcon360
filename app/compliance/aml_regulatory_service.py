"""
AML Regulatory Service — the engine behind the regulatory-submission and
program-governance capabilities.

Read-only use of the wallet ``TransactionModel`` for cash/structuring detection
keeps this compliant with the "wallet is high-risk, do not modify" rule. All
new state lives in the ``aml_regulatory_models`` tables.
"""
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any

from flask import current_app
from app.extensions import db
from app.compliance.aml_regulatory_models import (
    JurisdictionProfile,
    RegulatoryReport,
    CtrAlert,
    TerminatedEntity,
    OrganisationAmlProfile,
    MonitoringScenario,
    AmlBacktestRun,
    RetentionPolicy,
)


# ---------------------------------------------------------------------------
# Jurisdiction configuration (internationalisation layer)
# ---------------------------------------------------------------------------
# FATF-aligned baselines. Larger regimes override thresholds / SLAs / report
# types / identifiers. Unknown or smaller jurisdictions fall back to ``INT``.
_JURISDICTIONS = {
    'INT': dict(country_code='INT', country_name='International (FATF Baseline)',
                currency_code='USD', cash_threshold_amount=15000, str_sla_working_days=2,
                structuring_band_percent=10,
                supported_report_types=['str', 'sar', 'ctr', 'lctr', 'iwtr', 'tfr'],
                identifier_types=['tin'], retention_years=5, is_default=True),
    'UG': dict(country_code='UG', country_name='Uganda', currency_code='UGX',
               cash_threshold_amount=20000000, currency_point_value=20000, cash_threshold_points=1000,
               str_sla_working_days=2, structuring_band_percent=10,
               supported_report_types=['str', 'sar', 'ctr', 'lctr', 'iwtr', 'tfr', 'alctr'],
               identifier_types=['nin', 'ursb'], retention_years=10),
    'KE': dict(country_code='KE', country_name='Kenya', currency_code='KES',
               cash_threshold_amount=1000000, str_sla_working_days=3, structuring_band_percent=10,
               supported_report_types=['str', 'sar', 'ctr', 'iwtr', 'tfr'],
               identifier_types=['id_number', 'kra_pin'], retention_years=10),
    'TZ': dict(country_code='TZ', country_name='Tanzania', currency_code='TZS',
               cash_threshold_amount=10000000, str_sla_working_days=1, structuring_band_percent=10,
               supported_report_types=['str', 'sar', 'ctr', 'iwtr', 'tfr'],
               identifier_types=['nida'], retention_years=10),
    'ZM': dict(country_code='ZM', country_name='Zambia', currency_code='ZMW',
               cash_threshold_amount=500000, str_sla_working_days=2, structuring_band_percent=10,
               supported_report_types=['str', 'sar', 'ctr', 'iwtr', 'tfr'],
               identifier_types=['nrc', 'tin'], retention_years=10),
    'RW': dict(country_code='RW', country_name='Rwanda', currency_code='RWF',
               cash_threshold_amount=10000000, str_sla_working_days=2, structuring_band_percent=10,
               supported_report_types=['str', 'sar', 'ctr', 'iwtr', 'tfr'],
               identifier_types=['national_id'], retention_years=10),
    'NG': dict(country_code='NG', country_name='Nigeria', currency_code='NGN',
               cash_threshold_amount=5000000, str_sla_working_days=2, structuring_band_percent=10,
               supported_report_types=['str', 'sar', 'ctr', 'iwtr', 'tfr'],
               identifier_types=['bvn', 'tin'], retention_years=10),
    'GH': dict(country_code='GH', country_name='Ghana', currency_code='GHS',
               cash_threshold_amount=15000, str_sla_working_days=2, structuring_band_percent=10,
               supported_report_types=['str', 'sar', 'ctr', 'iwtr', 'tfr'],
               identifier_types=['ghana_card'], retention_years=10),
    'ZA': dict(country_code='ZA', country_name='South Africa', currency_code='ZAR',
               cash_threshold_amount=24900, str_sla_working_days=2, structuring_band_percent=10,
               supported_report_types=['str', 'sar', 'ctr', 'iwtr', 'tfr'],
               identifier_types=['id_number', 'tax_number'], retention_years=5),
    'GB': dict(country_code='GB', country_name='United Kingdom', currency_code='GBP',
               cash_threshold_amount=10000, str_sla_working_days=2, structuring_band_percent=10,
               supported_report_types=['str', 'sar', 'ctr', 'iwtr', 'tfr'],
               identifier_types=['nino', 'utr'], retention_years=6),
    'US': dict(country_code='US', country_name='United States', currency_code='USD',
               cash_threshold_amount=10000, str_sla_working_days=1, structuring_band_percent=10,
               supported_report_types=['str', 'sar', 'ctr', 'iwtr', 'tfr'],
               identifier_types=['ssn', 'tin'], retention_years=5),
    'EU': dict(country_code='EU', country_name='European Union', currency_code='EUR',
               cash_threshold_amount=10000, str_sla_working_days=2, structuring_band_percent=10,
               supported_report_types=['str', 'sar', 'ctr', 'iwtr', 'tfr'],
               identifier_types=['tin'], retention_years=5),
}


def seed_jurisdictions() -> int:
    """Idempotently create jurisdiction profiles. Returns number created."""
    created = 0
    for code, data in _JURISDICTIONS.items():
        if JurisdictionProfile.query.filter_by(country_code=code).first():
            continue
        profile = JurisdictionProfile(
            public_id=str(uuid.uuid4()),
            country_code=data['country_code'],
            country_name=data['country_name'],
            currency_code=data['currency_code'],
            cash_threshold_amount=Decimal(str(data['cash_threshold_amount'])),
            currency_point_value=Decimal(str(data['currency_point_value'])) if data.get('currency_point_value') else None,
            cash_threshold_points=Decimal(str(data['cash_threshold_points'])) if data.get('cash_threshold_points') else None,
            str_sla_working_days=data['str_sla_working_days'],
            structuring_band_percent=data['structuring_band_percent'],
            supported_report_types=data['supported_report_types'],
            identifier_types=data['identifier_types'],
            retention_years=data['retention_years'],
            is_default=bool(data.get('is_default', False)),
            is_active=True,
        )
        db.session.add(profile)
        created += 1
    if created:
        db.session.commit()
    return created


def get_default_jurisdiction() -> Optional[JurisdictionProfile]:
    profile = JurisdictionProfile.query.filter_by(is_default=True, is_active=True).first()
    if not profile:
        profile = JurisdictionProfile.query.filter_by(is_active=True).first()
    return profile


def get_jurisdiction(country_code: Optional[str]) -> JurisdictionProfile:
    if country_code:
        profile = JurisdictionProfile.query.filter_by(country_code=country_code.upper(), is_active=True).first()
        if profile:
            return profile
    return get_default_jurisdiction()


def list_jurisdictions() -> List[JurisdictionProfile]:
    return JurisdictionProfile.query.filter_by(is_active=True).order_by(
        JurisdictionProfile.is_default.desc(),
        JurisdictionProfile.country_name.asc()
    ).all()


# ---------------------------------------------------------------------------
# Working-day SLA computation
# ---------------------------------------------------------------------------
def compute_due_date(suspicion_formed_at: datetime, working_days: int,
                     jurisdiction: Optional[JurisdictionProfile] = None) -> datetime:
    """Return the SLA due datetime by advancing ``working_days`` business days."""
    if jurisdiction is None:
        jurisdiction = get_default_jurisdiction()
    sla = int(working_days if working_days is not None else
              (jurisdiction.str_sla_working_days if jurisdiction else 2))
    cursor = suspicion_formed_at or datetime.now(timezone.utc)
    remaining = sla
    while remaining > 0:
        cursor = cursor + timedelta(days=1)
        if cursor.weekday() < 5:  # Monday=0 .. Friday=4
            remaining -= 1
    return cursor


# ---------------------------------------------------------------------------
# Regulatory report building + goAML-style serialisation
# ---------------------------------------------------------------------------
def generate_report_number(jurisdiction: JurisdictionProfile, report_type: str) -> str:
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
    suffix = uuid.uuid4().hex[:6].upper()
    return f"{jurisdiction.country_code}-{report_type.upper()}-{stamp}-{suffix}"


def create_regulatory_report(
    report_type: str,
    subject_type: str = 'individual',
    subject_user_id: Optional[int] = None,
    subject_org_id: Optional[int] = None,
    subject_identifier: Optional[str] = None,
    subject_name: Optional[str] = None,
    related_transaction_id: Optional[str] = None,
    risk_score: Optional[float] = None,
    narrative: Optional[str] = None,
    amount: Optional[float] = None,
    currency_code: Optional[str] = None,
    suspicion_formed_at: Optional[datetime] = None,
    jurisdiction_code: Optional[str] = None,
    created_by: Optional[int] = None,
) -> RegulatoryReport:
    """Create a regulatory filing record with SLA due date and structured payload."""
    jurisdiction = get_jurisdiction(jurisdiction_code)
    suspicion_formed_at = suspicion_formed_at or datetime.now(timezone.utc)
    due_at = compute_due_date(suspicion_formed_at, jurisdiction.str_sla_working_days, jurisdiction)

    payload = {
        'report_type': report_type,
        'subject_type': subject_type,
        'subject_identifier': subject_identifier,
        'subject_name': subject_name,
        'related_transaction_id': related_transaction_id,
        'risk_score': risk_score,
        'amount': float(amount) if amount is not None else None,
        'currency_code': currency_code or (jurisdiction.currency_code if jurisdiction else None),
        'suspicion_formed_at': suspicion_formed_at.isoformat() if suspicion_formed_at else None,
        'due_at': due_at.isoformat() if due_at else None,
        'jurisdiction': jurisdiction.country_code if jurisdiction else None,
    }

    report = RegulatoryReport(
        public_id=str(uuid.uuid4()),
        report_number=generate_report_number(jurisdiction, report_type),
        jurisdiction_id=jurisdiction.id if jurisdiction else None,
        report_type=report_type,
        status='draft',
        subject_type=subject_type,
        subject_user_id=subject_user_id,
        subject_org_id=subject_org_id,
        subject_identifier=subject_identifier,
        subject_name=subject_name,
        related_transaction_id=related_transaction_id,
        risk_score=risk_score,
        narrative=narrative,
        amount=Decimal(str(amount)) if amount is not None else None,
        currency_code=currency_code or (jurisdiction.currency_code if jurisdiction else None),
        suspicion_formed_at=suspicion_formed_at,
        due_at=due_at,
        payload=payload,
    )
    db.session.add(report)
    # Generate goAML-style XML immediately so it is submission-ready.
    report.xml_content = generate_goaml_xml(report)
    db.session.commit()
    return report


def generate_goaml_xml(report: RegulatoryReport) -> str:
    """Produce a goAML-style XML representation of a regulatory report.

    This is a documentation/submission-ready serialisation; the exact FIA/Elmau
    schema mapping is configuration in ``RetentionPolicy``/jurisdiction tooling.
    """
    try:
        from xml.etree import ElementTree as ET
    except Exception:  # pragma: no cover
        return ''
    j = report.payload or {}
    root = ET.Element('goAML', {'version': '2.0', 'xmlns': 'http://goaml.org'})
    hdr = ET.SubElement(root, 'ReportHeader')
    ET.SubElement(hdr, 'ReportType').text = (report.report_type or '').upper()
    ET.SubElement(hdr, 'ReportNumber').text = report.report_number
    ET.SubElement(hdr, 'Jurisdiction').text = j.get('jurisdiction')
    ET.SubElement(hdr, 'SubmissionDue').text = j.get('due_at')
    ET.SubElement(hdr, 'SuspicionFormed').text = j.get('suspicion_formed_at')
    if report.risk_score is not None:
        ET.SubElement(hdr, 'RiskScore').text = str(report.risk_score)

    subj = ET.SubElement(root, 'Subject')
    ET.SubElement(subj, 'SubjectType').text = report.subject_type
    ET.SubElement(subj, 'Identifier').text = report.subject_identifier or ''
    ET.SubElement(subj, 'Name').text = report.subject_name or ''
    if report.related_transaction_id:
        ET.SubElement(subj, 'RelatedTransaction').text = report.related_transaction_id

    act = ET.SubElement(root, 'Activity')
    ET.SubElement(act, 'Amount').text = str(report.amount) if report.amount is not None else ''
    ET.SubElement(act, 'Currency').text = report.currency_code or ''

    narr = ET.SubElement(root, 'Narrative')
    narr.text = report.narrative or ''

    return ET.tostring(root, encoding='unicode')


# ---------------------------------------------------------------------------
# Large-cash (CTR) and structuring detection engine
# ---------------------------------------------------------------------------
from sqlalchemy import func  # noqa: E402
from app.wallet.models.transaction import TransactionModel  # noqa: E402  (read-only)


def detect_cash_and_structuring(user_id: Optional[int] = None, day=None,
                                jurisdiction_code: Optional[str] = None) -> List[CtrAlert]:
    """Aggregate completed transactions per user per day and raise CTR / structuring alerts.

    - CTR: aggregated amount >= jurisdiction cash threshold.
    - Structuring: aggregated amount within ``structuring_band_percent`` below the
      threshold across >= 2 transactions (smurfing / threshold-avoidance).
    """
    jurisdiction = get_jurisdiction(jurisdiction_code)
    threshold = Decimal(str(jurisdiction.cash_threshold_amount)) if jurisdiction else Decimal('0')
    band = Decimal(str(jurisdiction.structuring_band_percent)) if jurisdiction else Decimal('0')
    lower = threshold * (Decimal('1') - band / Decimal('100')) if threshold else Decimal('0')

    query = db.session.query(
        TransactionModel.user_id,
        func.coalesce(func.sum(TransactionModel.amount), 0),
        func.count(TransactionModel.id),
    ).filter(TransactionModel.status == 'completed')
    if user_id:
        query = query.filter(TransactionModel.user_id == user_id)
    if day:
        query = query.filter(func.date(TransactionModel.created_at) == day)
    rows = query.group_by(TransactionModel.user_id).all()

    created_alerts: List[CtrAlert] = []
    for uid, total, count in rows:
        if not uid or total is None:
            continue
        total = Decimal(str(total))
        period = (day or datetime.now(timezone.utc).date())
        existing = CtrAlert.query.filter_by(
            user_id=uid, period_date=period, status='open'
        ).first()
        if total >= threshold:
            if existing and existing.alert_type == 'ctr':
                continue
            alert = CtrAlert(
                public_id=str(uuid.uuid4()),
                user_id=uid,
                jurisdiction_id=jurisdiction.id if jurisdiction else None,
                alert_type='ctr',
                period_date=period,
                aggregated_amount=total,
                transaction_count=int(count),
                threshold_amount=threshold,
                status='open',
                details={'threshold': str(threshold), 'band': str(band)},
            )
            db.session.add(alert)
            created_alerts.append(alert)
        elif lower <= total < threshold and int(count) >= 2:
            if existing and existing.alert_type == 'structuring':
                continue
            alert = CtrAlert(
                public_id=str(uuid.uuid4()),
                user_id=uid,
                jurisdiction_id=jurisdiction.id if jurisdiction else None,
                alert_type='structuring',
                period_date=period,
                aggregated_amount=total,
                transaction_count=int(count),
                threshold_amount=threshold,
                status='open',
                details={'threshold': str(threshold), 'lower_band': str(lower)},
            )
            db.session.add(alert)
            created_alerts.append(alert)
    if created_alerts:
        db.session.commit()
    return created_alerts


# ---------------------------------------------------------------------------
# Terminated-merchant / high-risk entity screening (MATCH / VMSS equivalent)
# ---------------------------------------------------------------------------
def add_terminated_entity(name: str, entity_type: str = 'organisation',
                          registration_number: Optional[str] = None,
                          national_id: Optional[str] = None,
                          source: str = 'manual', reason_code: Optional[str] = None,
                          reason_text: Optional[str] = None,
                          terminated_at: Optional[datetime] = None,
                          added_by: Optional[int] = None) -> TerminatedEntity:
    entity = TerminatedEntity(
        public_id=str(uuid.uuid4()),
        entity_type=entity_type,
        name=name,
        registration_number=registration_number,
        national_id=national_id,
        source=source,
        reason_code=reason_code,
        reason_text=reason_text,
        terminated_at=terminated_at or datetime.now(timezone.utc),
        added_by=added_by,
        is_active=True,
    )
    db.session.add(entity)
    db.session.commit()
    return entity


def screen_organisation(organisation_id: int) -> List[TerminatedEntity]:
    """Check an organisation (and its AML profile identifiers) against the terminated registry."""
    from app.identity.models.organisation import Organisation
    org = db.session.get(Organisation, organisation_id)
    if not org:
        return []
    identifiers = []
    if getattr(org, 'registration_number', None):
        identifiers.append(('registration_number', org.registration_number))
    profile = OrganisationAmlProfile.query.filter_by(organisation_id=organisation_id).first()
    if profile:
        if profile.ursb_registration:
            identifiers.append(('registration_number', profile.ursb_registration))
        if profile.nin:
            identifiers.append(('national_id', profile.nin))

    hits: List[TerminatedEntity] = []
    for field, value in identifiers:
        if not value:
            continue
        match = TerminatedEntity.query.filter(
            getattr(TerminatedEntity, field) == value,
            TerminatedEntity.is_active == True  # noqa: E712
        ).first()
        if match and match not in hits:
            hits.append(match)
    return hits


# ---------------------------------------------------------------------------
# Application-level integrity for logical references (no DB FK)
# ---------------------------------------------------------------------------
def validate_screening_result_link(screening_result_id: Optional[int]) -> bool:
    """Best-effort existence check before linking a screening result.

    ``OrganisationAmlProfile.screening_result_id`` is now a proper enforced FK,
    so the database already guarantees referential integrity. This helper is
    defense-in-depth for code paths that build the link before commit.
    """
    if screening_result_id is None:
        return True
    try:
        from app.compliance.aml_service import AMLScreeningResult
        return AMLScreeningResult.query.get(screening_result_id) is not None
    except Exception:
        # If the screening store is unavailable, fail closed rather than
        # risk an unverifiable reference.
        return False


def find_orphan_screening_refs() -> List[OrganisationAmlProfile]:
    """Detect OrganisationAmlProfile rows whose screening_result_id is dangling.

    With the FK now enforced this should normally return empty; retained as a
    periodic compliance-QA check to catch any hard-delete/restore edge cases.
    """
    orphans: List[OrganisationAmlProfile] = []
    try:
        from app.compliance.aml_service import AMLScreeningResult
        profiles = OrganisationAmlProfile.query.filter(
            OrganisationAmlProfile.screening_result_id.isnot(None)
        ).all()
        valid_ids = {
            row.id for row in
            AMLScreeningResult.query.with_entities(AMLScreeningResult.id).all()
        }
        for p in profiles:
            if p.screening_result_id not in valid_ids:
                orphans.append(p)
    except Exception:
        return orphans
    return orphans


# ---------------------------------------------------------------------------
# Transaction-monitoring scenario calibration + back-testing
# ---------------------------------------------------------------------------
def evaluate_scenario(scenario: MonitoringScenario, context: Dict[str, Any]) -> int:
    """Return the risk-score contribution of a scenario given a transaction context."""
    if not scenario.is_enabled:
        return 0
    amount = context.get('amount')
    if scenario.category == 'amount' and scenario.threshold_value is not None and amount is not None:
        try:
            if Decimal(str(amount)) >= scenario.threshold_value:
                return int(scenario.risk_weight)
        except Exception:
            return 0
    return 0


def run_backtest(scenario_id: int, window_start: datetime, window_end: datetime) -> AmlBacktestRun:
    """Score historical transactions against a scenario; record alert yield for QA."""
    scenario = db.session.get(MonitoringScenario, scenario_id)
    run = AmlBacktestRun(
        public_id=str(uuid.uuid4()),
        scenario_id=scenario_id,
        window_start=window_start,
        window_end=window_end,
    )
    if not scenario:
        run.notes = 'Scenario not found'
        db.session.add(run)
        db.session.commit()
        return run

    txns = TransactionModel.query.filter(
        TransactionModel.created_at >= window_start,
        TransactionModel.created_at <= window_end,
    ).all()
    scored = 0
    alerts = 0
    for txn in txns:
        scored += 1
        alerts += 1 if evaluate_scenario(scenario, {'amount': txn.amount}) > 0 else 0
    run.transactions_scored = scored
    run.alerts_generated = alerts
    db.session.add(run)
    db.session.commit()
    return run


# ---------------------------------------------------------------------------
# Retention policy + program scorecard
# ---------------------------------------------------------------------------
def ensure_default_retention_policies() -> int:
    defaults = [
        ('kyc', 10), ('transaction', 10), ('regulatory_report', 10),
        ('aml_screening', 10), ('audit_log', 10),
    ]
    created = 0
    for rtype, years in defaults:
        if RetentionPolicy.query.filter_by(resource_type=rtype).first():
            continue
        db.session.add(RetentionPolicy(
            public_id=str(uuid.uuid4()),
            resource_type=rtype,
            retention_years=years,
            auto_purge=False,
            is_enabled=True,
        ))
        created += 1
    if created:
        db.session.commit()
    return created


def get_retention_summary() -> List[Dict[str, Any]]:
    policies = RetentionPolicy.query.filter_by(is_enabled=True).all()
    summary = []
    now = datetime.now(timezone.utc)
    for policy in policies:
        cutoff = now - timedelta(days=policy.retention_years * 365)
        aged = 0
        try:
            if policy.resource_type == 'transaction':
                aged = TransactionModel.query.filter(
                    TransactionModel.created_at < cutoff
                ).count()
        except Exception:
            aged = 0
        summary.append({
            'resource_type': policy.resource_type,
            'retention_years': policy.retention_years,
            'aged_records': aged,
            'auto_purge': policy.auto_purge,
        })
    return summary


def compliance_scorecard() -> Dict[str, Any]:
    """Program-level maturity snapshot used by docs and the compliance UI."""
    return {
        'jurisdictions': JurisdictionProfile.query.filter_by(is_active=True).count(),
        'open_ctr_alerts': CtrAlert.query.filter_by(status='open').count(),
        'regulatory_reports': RegulatoryReport.query.count(),
        'overdue_reports': RegulatoryReport.query.filter(
            RegulatoryReport.due_at < datetime.now(timezone.utc),
            RegulatoryReport.status.in_(['draft', 'submitted'])
        ).count(),
        'terminated_entities': TerminatedEntity.query.filter_by(is_active=True).count(),
        'monitoring_scenarios': MonitoringScenario.query.filter_by(is_enabled=True).count(),
        'training_records': AmlTrainingRecord.query.count(),
        'attestations': AmlAttestation.query.count(),
        'retention_policies': RetentionPolicy.query.filter_by(is_enabled=True).count(),
    }
