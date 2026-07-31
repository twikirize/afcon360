"""
app/wallet/services/__init__.py
Wallet services module - business logic layer.
"""

# Core services
from app.wallet.services.wallet_service import WalletService
from app.wallet.services.currency_service import CurrencyService
from app.wallet.services.fx_service import FXService

# Admin & Compliance services
from app.wallet.services.admin_audit_service import AdminAuditService
from app.wallet.services.aggregator_service import AggregatorService
from app.wallet.services.commission_service import CommissionService
from app.wallet.services.compliance_engine import (
    ComplianceEngine,
    ComplianceResult,
    ComplianceCheck,
    ComplianceRuleType,
    ComplianceAction,
    RiskLevel,
    CountryComplianceConfig,
    SanctionsService,
    AMLTransactionMonitor,
    check_transaction,
    is_sanctioned,
    should_report_str,
    get_country_requirements
)

# Fraud & Security services
from app.wallet.services.fraud_detection_service import FraudDetectionService
from app.wallet.services.kyc_limit_service import KYCLimitService
from app.wallet.services.identity_verification_service import IdentityVerificationService
from app.wallet.services.suspicious_activity_service import SuspiciousActivityService
from app.wallet.services.nonce_protection_service import NonceProtectionService
from app.wallet.services.travel_rule_service import TravelRuleService

# Payment services
from app.wallet.services.payment_gateway import (
    PaymentProvider,
    PaymentMethod,
    PaymentRequest,
    PaymentResponse,
    PayoutRequest,
    PayoutResponse,
    BasePaymentGateway,
    FlutterwaveGateway,
    PaystackGateway,
    PaymentGatewayFactory,
    PaymentOrchestrator,
    get_payment_orchestrator,
    deposit_with_card,
    deposit_with_mobile_money,
    deposit_with_bank_transfer,
    withdraw_to_bank,
    withdraw_to_mobile_money,
    verify_payment,
    verify_payout,
    handle_provider_webhook,
    get_recommended_providers,
    is_provider_available,
    get_provider_status
)

# Payout & Reconciliation services
from app.wallet.services.payout_service import PayoutService
from app.wallet.services.reconciliation_service import ReconciliationService

# Regulatory services
from app.wallet.services.regulator_service import RegulatorService
from app.wallet.services.regulatory_reporting import (
    STRReport,
    CTRReport,
    RegulatoryReportingService,
    generate_str_report,
    generate_ctr_report
)

# Wallet status service
from app.wallet.services.wallet_status_service import (
    WalletStatusService,
    WalletStatus,
    WalletTier,
    WalletFeature
)

# Webhook service
from app.wallet.services.webhook_service import WebhookService

# Notifications
from app.wallet.services.wallet_notifications import (
    notify_deposit,
    notify_transfer_sent,
    notify_transfer_received,
    notify_withdrawal_initiated,
    notify_withdrawal_completed,
    notify_withdrawal_failed,
    notify_pin_locked,
    notify_kyc_status_change,
    notify_admin_adjustment,
    notify_adjustment_requested,
    notify_adjustment_approved,
    notify_reconciliation_alert
)

__all__ = [
    # Core services
    'WalletService',
    'CurrencyService',
    'FXService',

    # Admin & Compliance
    'AdminAuditService',
    'AggregatorService',
    'CommissionService',
    'ComplianceEngine',
    'ComplianceResult',
    'ComplianceCheck',
    'ComplianceRuleType',
    'ComplianceAction',
    'RiskLevel',
    'CountryComplianceConfig',
    'SanctionsService',
    'AMLTransactionMonitor',
    'check_transaction',
    'is_sanctioned',
    'should_report_str',
    'get_country_requirements',

    # Fraud & Security
    'FraudDetectionService',
    'NonceProtectionService',
    'TravelRuleService',

    # Payment Gateway
    'PaymentProvider',
    'PaymentMethod',
    'PaymentRequest',
    'PaymentResponse',
    'PayoutRequest',
    'PayoutResponse',
    'BasePaymentGateway',
    'FlutterwaveGateway',
    'PaystackGateway',
    'PaymentGatewayFactory',
    'PaymentOrchestrator',
    'get_payment_orchestrator',
    'deposit_with_card',
    'deposit_with_mobile_money',
    'deposit_with_bank_transfer',
    'withdraw_to_bank',
    'withdraw_to_mobile_money',
    'verify_payment',
    'verify_payout',
    'handle_provider_webhook',
    'get_recommended_providers',
    'is_provider_available',
    'get_provider_status',

    # Payout & Reconciliation
    'PayoutService',
    'ReconciliationService',

    # Regulatory
    'RegulatorService',
    'STRReport',
    'CTRReport',
    'RegulatoryReportingService',
    'generate_str_report',
    'generate_ctr_report',

    # Wallet Status
    'WalletStatusService',
    'WalletStatus',
    'WalletTier',
    'WalletFeature',

    # Webhook
    'WebhookService',

    # Notifications
    'notify_deposit',
    'notify_transfer_sent',
    'notify_transfer_received',
    'notify_withdrawal_initiated',
    'notify_withdrawal_completed',
    'notify_withdrawal_failed',
    'notify_pin_locked',
    'notify_kyc_status_change',
    'notify_admin_adjustment',
    'notify_adjustment_requested',
    'notify_adjustment_approved',
    'notify_reconciliation_alert',
]