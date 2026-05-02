"""
Cross-Border Compliance Engine
AML/KYC per country, sanctions screening, regulatory reporting
"""

from enum import Enum
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
from flask import current_app

from app.extensions import db, redis_client
from app.wallet.models.transaction import TransactionModel, TransactionType, TransactionStatus
from app.wallet.models.audit import AuditLogModel
from app.identity.models.user import User


class ComplianceRuleType(Enum):
    KYC_REQUIRED = "kyc_required"
    TRANSACTION_LIMIT = "transaction_limit"
    COUNTRY_RESTRICTED = "country_restricted"
    CURRENCY_RESTRICTED = "currency_restricted"
    SANCTIONS_SCREENING = "sanctions_screening"
    AML_THRESHOLD = "aml_threshold"
    SOURCE_OF_FUNDS = "source_of_funds"
    BUSINESS_VERIFICATION = "business_verification"


class ComplianceAction(Enum):
    ALLOW = "allow"
    BLOCK = "block"
    REVIEW = "review"
    REQUEST_DOCUMENTS = "request_documents"
    FREEZE_ACCOUNT = "freeze_account"
    NOTIFY_COMPLIANCE = "notify_compliance"


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ComplianceCheck:
    rule_type: ComplianceRuleType
    passed: bool
    action: ComplianceAction
    risk_level: RiskLevel
    message: str
    details: Optional[Dict[str, Any]] = None


@dataclass
class ComplianceResult:
    can_proceed: bool
    checks: List[ComplianceCheck]
    overall_risk: RiskLevel
    required_actions: List[ComplianceAction]
    user_blocked: bool
    requires_manual_review: bool


class CountryComplianceConfig:
    """Compliance configuration per country"""
    
    KYC_REQUIREMENTS = {
        "NG": {
            "bvn_required": True,
            "nin_required": False,
            "address_verification": True,
            "phone_verification": True,
            "daily_limit_ngn": 500000,
            "daily_limit_ngn_with_bvn": 5000000,
            "annual_limit_usd": 10000,
        },
        "UG": {
            "nin_required": True,
            "address_verification": True,
            "phone_verification": True,
            "daily_limit_ugx": 4000000,
            "annual_limit_usd": 10000,
        },
        "KE": {
            "national_id_required": True,
            "kra_pin_required": True,
            "address_verification": True,
            "daily_limit_kes": 140000,
            "annual_limit_usd": 10000,
        },
        "GH": {
            "ghana_card_required": True,
            "address_verification": True,
            "daily_limit_ghs": 10000,
            "annual_limit_usd": 10000,
        },
        "ZA": {
            "id_number_required": True,
            "fica_required": True,
            "address_verification": True,
            "daily_limit_zar": 100000,
            "annual_limit_usd": 10000,
        },
        "GB": {
            "address_verification": True,
            "source_of_funds_required": True,
            "daily_limit_gbp": 10000,
            "annual_limit_usd": 50000,
        },
        "US": {
            "ssn_required": False,
            "address_verification": True,
            "source_of_funds_required": True,
            "ofac_screening": True,
            "daily_limit_usd": 10000,
            "annual_limit_usd": 50000,
        },
        "EU": {
            "address_verification": True,
            "source_of_funds_required": True,
            "gdpr_compliance": True,
            "daily_limit_eur": 10000,
            "annual_limit_usd": 50000,
        }
    }
    
    RESTRICTED_COUNTRIES = ["IR", "KP", "SY", "CU", "MM"]
    HIGH_RISK_COUNTRIES = ["AF", "BY", "CF", "TD", "SO", "SS", "YE"]
    
    RESTRICTED_CURRENCIES = {
        "NG": ["USD"],
        "ZW": ["ZWL"],
    }
    
    @classmethod
    def get_requirements(cls, country_code: str) -> Dict:
        return cls.KYC_REQUIREMENTS.get(country_code, cls.KYC_REQUIREMENTS.get("EU", {}))
    
    @classmethod
    def is_country_restricted(cls, country_code: str) -> bool:
        return country_code in cls.RESTRICTED_COUNTRIES
    
    @classmethod
    def is_country_high_risk(cls, country_code: str) -> bool:
        return country_code in cls.HIGH_RISK_COUNTRIES
    
    @classmethod
    def is_currency_restricted(cls, country_code: str, currency: str) -> bool:
        restricted = cls.RESTRICTED_CURRENCIES.get(country_code, [])
        return currency in restricted


class SanctionsService:
    """Sanctions list screening service"""
    
    @classmethod
    def screen_name(cls, name: str) -> Tuple[bool, Optional[str]]:
        name_hash = hashlib.sha256(name.lower().encode()).hexdigest()
        cache_key = f"sanctions:{name_hash}"
        cached_result = redis_client.get(cache_key)
        
        if cached_result:
            result = json.loads(cached_result)
            return result.get("match"), result.get("list")
        
        is_match = False
        matched_list = None
        
        redis_client.setex(cache_key, 86400, json.dumps({
            "match": is_match,
            "list": matched_list
        }))
        
        return is_match, matched_list
    
    @classmethod
    def screen_transaction(cls, sender_name: str, recipient_name: str, 
                          amount: float, currency: str) -> Tuple[bool, Optional[str]]:
        sender_match, sender_list = cls.screen_name(sender_name)
        recipient_match, recipient_list = cls.screen_name(recipient_name)
        
        if sender_match:
            return True, f"Sender match: {sender_list}"
        if recipient_match:
            return True, f"Recipient match: {recipient_list}"
        
        return False, None


class AMLTransactionMonitor:
    """AML transaction monitoring"""
    
    DAILY_REPORTING_THRESHOLD = 10000
    
    @classmethod
    def calculate_user_volume(cls, user_id: int, days: int = 1) -> Dict:
        from_date = datetime.utcnow() - timedelta(days=days)
        
        transactions = TransactionModel.query.filter(
            TransactionModel.user_id == user_id,
            TransactionModel.created_at >= from_date,
            TransactionModel.status == TransactionStatus.COMPLETED,
            TransactionModel.is_deleted == False
        ).all()
        
        total_count = len(transactions)
        total_amount_usd = sum(tx.amount for tx in transactions if tx.currency == "USD")
        
        return {
            "count": total_count,
            "amount_usd": total_amount_usd,
            "transactions": transactions
        }
    
    @classmethod
    def check_suspicious_patterns(cls, user_id: int, transaction: TransactionModel) -> List[Dict]:
        alerts = []
        volume_data = cls.calculate_user_volume(user_id, days=1)
        
        if 9000 <= transaction.amount <= 9999:
            recent_structuring = sum(1 for tx in volume_data["transactions"] 
                                      if 9000 <= tx.amount <= 9999)
            if recent_structuring >= 3:
                alerts.append({
                    "pattern": "structuring",
                    "severity": "high",
                    "description": f"User has {recent_structuring} transactions near reporting threshold"
                })
        
        recent_txns = [tx for tx in volume_data["transactions"]
                      if (datetime.utcnow() - tx.created_at).total_seconds() < 300]
        if len(recent_txns) >= 5:
            alerts.append({
                "pattern": "rapid_succession",
                "severity": "medium",
                "description": f"{len(recent_txns)} transactions in 5 minutes"
            })
        
        return alerts
    
    @classmethod
    def should_file_str(cls, user_id: int, transaction: TransactionModel) -> bool:
        alerts = cls.check_suspicious_patterns(user_id, transaction)
        high_severity = [a for a in alerts if a["severity"] == "high"]
        return len(high_severity) > 0 or transaction.amount >= cls.DAILY_REPORTING_THRESHOLD


class ComplianceEngine:
    """Main compliance engine"""
    
    def __init__(self):
        self.config = CountryComplianceConfig()
        self.sanctions = SanctionsService()
        self.aml = AMLTransactionMonitor()
    
    def check_transaction_compliance(self, user_id: int, amount: float, 
                                       currency: str, transaction_type: TransactionType,
                                       recipient_country: str = None,
                                       source_country: str = None) -> ComplianceResult:
        checks = []
        required_actions = []
        
        user = User.query.get(user_id)
        if not user:
            return ComplianceResult(
                can_proceed=False,
                checks=[ComplianceCheck(
                    rule_type=ComplianceRuleType.KYC_REQUIRED,
                    passed=False,
                    action=ComplianceAction.BLOCK,
                    risk_level=RiskLevel.CRITICAL,
                    message="User not found"
                )],
                overall_risk=RiskLevel.CRITICAL,
                required_actions=[ComplianceAction.BLOCK],
                user_blocked=True,
                requires_manual_review=False
            )
        
        if source_country and self.config.is_country_restricted(source_country):
            checks.append(ComplianceCheck(
                rule_type=ComplianceRuleType.COUNTRY_RESTRICTED,
                passed=False,
                action=ComplianceAction.BLOCK,
                risk_level=RiskLevel.CRITICAL,
                message=f"Transactions from {source_country} are prohibited"
            ))
            required_actions.append(ComplianceAction.BLOCK)
        
        country_reqs = self.config.get_requirements(source_country or "NG")
        
        missing_requirements = []
        if country_reqs.get("bvn_required") and not getattr(user, 'bvn_verified', False):
            missing_requirements.append("BVN")
        if country_reqs.get("nin_required") and not getattr(user, 'nin_verified', False):
            missing_requirements.append("NIN")
        
        if missing_requirements:
            checks.append(ComplianceCheck(
                rule_type=ComplianceRuleType.KYC_REQUIRED,
                passed=False,
                action=ComplianceAction.REQUEST_DOCUMENTS,
                risk_level=RiskLevel.MEDIUM,
                message=f"Missing KYC: {', '.join(missing_requirements)}"
            ))
            required_actions.append(ComplianceAction.REQUEST_DOCUMENTS)
        
        if amount >= self.aml.DAILY_REPORTING_THRESHOLD:
            checks.append(ComplianceCheck(
                rule_type=ComplianceRuleType.AML_THRESHOLD,
                passed=True,
                action=ComplianceAction.NOTIFY_COMPLIANCE,
                risk_level=RiskLevel.MEDIUM,
                message=f"Transaction exceeds reporting threshold: {amount}"
            ))
            required_actions.append(ComplianceAction.NOTIFY_COMPLIANCE)
        
        can_proceed = ComplianceAction.BLOCK not in required_actions
        user_blocked = ComplianceAction.FREEZE_ACCOUNT in required_actions
        requires_review = ComplianceAction.REVIEW in required_actions
        
        risk_levels = [c.risk_level for c in checks] if checks else [RiskLevel.LOW]
        overall_risk = max(risk_levels, key=lambda x: [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL].index(x))
        
        return ComplianceResult(
            can_proceed=can_proceed,
            checks=checks,
            overall_risk=overall_risk,
            required_actions=list(set(required_actions)),
            user_blocked=user_blocked,
            requires_manual_review=requires_review
        )


def check_transaction(user_id: int, amount: float, currency: str,
                      transaction_type: str = "transfer",
                      recipient_country: str = None,
                      source_country: str = None) -> ComplianceResult:
    engine = ComplianceEngine()
    tx_type = TransactionType(transaction_type) if transaction_type else TransactionType.TRANSFER
    
    return engine.check_transaction_compliance(
        user_id=user_id,
        amount=amount,
        currency=currency,
        transaction_type=tx_type,
        recipient_country=recipient_country,
        source_country=source_country
    )


def is_sanctioned(name: str) -> Tuple[bool, Optional[str]]:
    return SanctionsService.screen_name(name)


def should_report_str(user_id: int, amount: float) -> bool:
    return AMLTransactionMonitor.should_file_str(user_id, amount)


def get_country_requirements(country_code: str) -> Dict:
    return CountryComplianceConfig.get_requirements(country_code)


__all__ = [
    'ComplianceEngine', 'ComplianceResult', 'ComplianceCheck',
    'ComplianceRuleType', 'ComplianceAction', 'RiskLevel',
    'CountryComplianceConfig', 'SanctionsService', 'AMLTransactionMonitor',
    'check_transaction', 'is_sanctioned', 'should_report_str', 'get_country_requirements'
]
