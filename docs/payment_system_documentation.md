# AFCON360 Payment System Documentation

## Overview

AFCON360 provides a comprehensive, multi-gateway payment system designed for African markets with global reach. The system supports multiple payment methods, regulatory compliance, and real-time transaction monitoring.

## Table of Contents

1. [Supported Payment Gateways](#supported-payment-gateways)
2. [Regional Coverage](#regional-coverage)
3. [Technical Architecture](#technical-architecture)
4. [Security & Compliance](#security--compliance)
5. [API Documentation](#api-documentation)
6. [Configuration](#configuration)
7. [Troubleshooting](#troubleshooting)

## Supported Payment Gateways

### Global Payment Methods

#### PayPal
- **Regions**: Global
- **Currencies**: USD, EUR, GBP, JPY, CAD, AUD
- **Transaction Types**: Deposits, Withdrawals
- **Features**: 3D Secure, Buyer/Seller Protection
- **Fees**: 2.9% + $0.30 fixed
- **Environment**: Sandbox/Production

#### Alipay
- **Regions**: China, Southeast Asia
- **Currencies**: CNY, USD, EUR
- **Transaction Types**: QR Code Payments, Mobile Payments
- **Features**: Real-time verification, QR code generation
- **Fees**: 0.6%
- **Environment**: Sandbox/Production

#### Visa Direct
- **Regions**: Global
- **Currencies**: USD, EUR, GBP, JPY, and 130+ more
- **Transaction Types**: Card-to-Card, P2P, B2B
- **Features**: 3D Secure, Tokenization, Real-time processing
- **Fees**: 1.8% + $0.10
- **Environment**: Sandbox/Production

### African Payment Methods

#### Flutterwave
- **Regions**: 30+ African countries
- **Currencies**: NGN, GHS, KES, UGX, ZAR, and 15+ more
- **Transaction Types**: Card, Mobile Money, Bank Transfer
- **Features**: Multi-currency, Local payment methods
- **Fees**: 1.4%
- **Environment**: Sandbox/Production

#### Paystack
- **Regions**: Nigeria, Ghana, South Africa
- **Currencies**: NGN, GHS, ZAR
- **Transaction Types**: Card, Bank Transfer, Mobile Money
- **Features**: Recurring payments, Subscription billing
- **Fees**: 1.5%
- **Environment**: Sandbox/Production

#### Mobile Money Services

**MTN Mobile Money**
- **Countries**: Uganda, Nigeria, Ghana, Cameroon
- **Currencies**: UGX, NGN, GHS, XAF
- **Features**: USSD, Agent network, Instant transfers
- **Fees**: 1.0%

**Airtel Money**
- **Countries**: Uganda, Nigeria, Ghana, Kenya, Tanzania
- **Currencies**: UGX, NGN, GHS, KES, TZS
- **Features**: Cross-border transfers, Bill payments
- **Fees**: 1.0%

**M-PESA**
- **Countries**: Kenya, Tanzania, Mozambique, DRC
- **Currencies**: KES, TZS, MZN, CDF
- **Features**: STK Push, Lipa na M-PESA, Till payments
- **Fees**: 1.0%

#### WeChat Pay
- **Regions**: China, International
- **Currencies**: CNY, USD, EUR
- **Transaction Types**: QR Code, Mini-program payments
- **Features**: Social payments, Integration with WeChat ecosystem
- **Fees**: 0.6%
- **Environment**: Sandbox/Production

## Regional Coverage

### East Africa
- **Kenya**: M-PESA, Airtel Money, Flutterwave, Paystack
- **Uganda**: MTN Mobile Money, Airtel Money, Flutterwave
- **Tanzania**: M-PESA, Airtel Money, Tigo Pesa
- **Rwanda**: MTN Mobile Money, Airtel Money
- **Burundi**: EcoCash, Lumicash

### West Africa
- **Nigeria**: Paystack, Flutterwave, MTN Mobile Money, Airtel Money
- **Ghana**: MTN Mobile Money, Airtel Money, Vodafone Cash
- **Côte d'Ivoire**: MTN Mobile Money, Orange Money, Wave
- **Burkina Faso**: MTN Mobile Money, Orange Money, Moov
- **Senegal**: Orange Money, Wari, Joni Joni

### North Africa
- **Egypt**: Fawry, ValU, Mobile Wallets
- **Morocco**: CIH Bank, Attijariwafa Bank, Cash Plus
- **Algeria**: CIB, BNA, Baridi Mob
- **Tunisia**: BIAT, STB, E-dinar

### Southern Africa
- **South Africa**: Visa, Mastercard, EFT, Ozow
- **Botswana**: Mobile Money, Bank Transfer
- **Zimbabwe**: EcoCash, OneMoney, ZIPIT
- **Zambia**: Airtel Money, MTN Mobile Money, Zamtel

## Technical Architecture

### System Components

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend     │    │   API Gateway  │    │   Payment      │
│   (Web/Mobile) │◄──►│   (Rate Limit   │◄──►│   Gateways     │
│                │    │    & Auth)     │    │                │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   User         │    │   Wallet        │    │   Audit &      │
│   Management   │    │   Service      │    │   Compliance   │
│                │    │                │    │                │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Data Flow

1. **Transaction Initiation**
   - User selects payment method
   - Frontend validates input
   - API Gateway authenticates request

2. **Payment Processing**
   - Wallet Service creates transaction record
   - Payment Gateway processes payment
   - Real-time status updates

3. **Completion**
   - Wallet balance updated
   - Audit trail created
   - User notified
   - Regulator notified (if required)

### Database Schema

#### Transactions Table
```sql
CREATE TABLE wallet_transactions (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    transaction_id VARCHAR(100) UNIQUE NOT NULL,
    user_id BIGINT NOT NULL,
    amount DECIMAL(15,2) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    status ENUM('pending', 'completed', 'failed', 'cancelled'),
    gateway_type VARCHAR(50),
    payment_method VARCHAR(100),
    provider_reference VARCHAR(200),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at)
);
```

#### Wallet Balances Table
```sql
CREATE TABLE wallet_balances (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT UNIQUE NOT NULL,
    balance DECIMAL(15,2) DEFAULT 0.00,
    currency VARCHAR(3) DEFAULT 'UGX',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id)
);
```

## Security & Compliance

### Security Measures

#### Encryption
- **Data at Rest**: AES-256 encryption
- **Data in Transit**: TLS 1.3
- **API Keys**: Encrypted storage with Fernet
- **Sensitive Data**: Field-level encryption

#### Authentication
- **Multi-Factor**: SMS/Email 2FA
- **Session Management**: JWT tokens with expiration
- **Rate Limiting**: Configurable per endpoint
- **IP Whitelisting**: For admin access

#### Audit Trail
- **Financial Transactions**: Complete audit trail
- **Admin Actions**: All changes logged
- **API Access**: Request/response logging
- **Compliance**: Regulatory reporting ready

### Compliance Features

#### Anti-Money Laundering (AML)
- **Transaction Monitoring**: Real-time screening
- **Suspicious Activity**: Automatic flagging
- **Threshold Alerts**: Configurable limits
- **Regulatory Reporting**: Automated reports

#### Know Your Customer (KYC)
- **Verification Levels**: 3-tier verification
- **Document Management**: Secure storage
- **Biometric Verification**: Optional
- **Risk Assessment**: Automated scoring

#### Regulatory Compliance
- **Data Retention**: 7-year retention policy
- **Access Control**: Role-based permissions
- **Reporting**: Automated compliance reports
- **Audit Logs**: Complete traceability

## API Documentation

### Authentication

#### API Key Authentication
```http
GET /api/v1/wallet/balance
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json
```

#### Regulator Access Code
```http
GET /api/v1/regulator/reports/daily
X-Access-Code: REG-ABC123DEF456
Content-Type: application/json
```

### Core Endpoints

#### Wallet Operations

**Get Balance**
```http
GET /api/v1/wallet/balance
```

Response:
```json
{
    "success": true,
    "balance": {
        "amount": 1000000.00,
        "currency": "UGX",
        "available": 950000.00,
        "frozen": 50000.00
    }
}
```

**Initiate Deposit**
```http
POST /api/v1/wallet/deposit
{
    "amount": 100000,
    "currency": "UGX",
    "gateway": "flutterwave",
    "payment_method": "mobile_money",
    "phone_number": "+256712345678"
}
```

Response:
```json
{
    "success": true,
    "transaction_id": "TXN-20250607-001",
    "provider_reference": "FLW-REF-123456",
    "status": "pending",
    "redirect_url": "https://flutterwave.com/pay/FLW-REF-123456"
}
```

**Initiate Withdrawal**
```http
POST /api/v1/wallet/withdraw
{
    "amount": 50000,
    "currency": "UGX",
    "gateway": "mobile_money",
    "phone_number": "+256712345678"
}
```

#### Payment Gateway Operations

**Process Payment**
```http
POST /api/v1/payments/process
{
    "transaction_id": "TXN-20250607-001",
    "gateway": "flutterwave",
    "payment_details": {
        "card_number": "****-****-****-1234",
        "expiry": "12/25",
        "cvv": "***"
    }
}
```

**Verify Webhook**
```http
POST /api/v1/payments/webhook/verify
{
    "gateway": "flutterwave",
    "signature": "sha256=abc123...",
    "payload": {...}
}
```

#### Regulator API

**Generate Access Code**
```http
POST /api/v1/regulator/generate-access
{
    "regulator_id": "bank_of_uganda",
    "permissions": ["report_daily", "report_weekly"],
    "duration_hours": 24
}
```

**Get Compliance Report**
```http
GET /api/v1/regulator/reports/daily?start_date=2025-06-01&end_date=2025-06-01
X-Access-Code: REG-ABC123DEF456
```

### Error Handling

#### Standard Error Response
```json
{
    "success": false,
    "error": "Insufficient balance",
    "error_code": "INSUFFICIENT_BALANCE",
    "transaction_id": "TXN-20250607-001",
    "timestamp": "2025-06-07T12:00:00Z"
}
```

#### Error Codes
- `INSUFFICIENT_BALANCE`: Wallet balance too low
- `INVALID_GATEWAY`: Payment gateway not supported
- `TRANSACTION_FAILED`: Payment processing failed
- `RATE_LIMIT_EXCEEDED`: Too many requests
- `INVALID_ACCESS_CODE`: Regulator access code invalid
- `INSUFFICIENT_PERMISSIONS`: User lacks required permissions

## Configuration

### Environment Variables

#### Database Configuration
```bash
DATABASE_URL=mysql://user:password@localhost:3306/afcon360
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=30
```

#### Payment Gateway Configuration
```bash
# PayPal
PAYPAL_CLIENT_ID=your_paypal_client_id
PAYPAL_CLIENT_SECRET=your_paypal_client_secret
PAYPAL_ENVIRONMENT=sandbox

# Flutterwave
FLUTTERWAVE_PUBLIC_KEY=your_flw_public_key
FLUTTERWAVE_SECRET_KEY=your_flw_secret_key
FLUTTERWAVE_ENVIRONMENT=sandbox

# Paystack
PAYSTACK_PUBLIC_KEY=your_paystack_public_key
PAYSTACK_SECRET_KEY=your_paystack_secret_key
PAYSTACK_ENVIRONMENT=sandbox

# Mobile Money
MTN_UG_API_KEY=your_mtn_ug_api_key
AIRTEL_UG_API_KEY=your_airtel_ug_api_key
MPESA_API_KEY=your_mpesa_api_key
MPESA_PASSKEY=your_mpesa_passkey
```

#### Security Configuration
```bash
JWT_SECRET_KEY=your_jwt_secret_key
ENCRYPTION_KEY=your_encryption_key
REGULATOR_ENCRYPTION_KEY=your_regulator_key
WEBHOOK_SECRET=your_webhook_secret
```

#### Compliance Configuration
```bash
AML_ENABLED=true
AML_THRESHOLD=1000000
KYC_ENABLED=true
AUDIT_RETENTION_DAYS=2555
REGULATOR_ACCESS_ENABLED=true
```

### Rate Limiting

#### Default Limits
- **Wallet Operations**: 100 requests/minute
- **Payment Processing**: 50 requests/minute
- **Regulator API**: 1000 requests/minute
- **Admin Operations**: 200 requests/minute

#### Custom Limits
```python
# app/config.py
RATE_LIMITS = {
    'wallet_balance': '100/minute',
    'wallet_deposit': '50/minute',
    'wallet_withdraw': '30/minute',
    'regulator_api': '1000/minute'
}
```

## Troubleshooting

### Common Issues

#### Payment Gateway Timeout
**Problem**: Payment gateway not responding
**Solution**: 
1. Check network connectivity
2. Verify API keys are correct
3. Check gateway status page
4. Increase timeout in configuration

#### Transaction Stuck in Pending
**Problem**: Transaction not completing
**Solution**:
1. Check webhook URL accessibility
2. Verify webhook signature
3. Check transaction logs for errors
4. Manually verify with gateway

#### Balance Discrepancy
**Problem**: Wallet balance incorrect
**Solution**:
1. Check transaction history
2. Verify audit logs
3. Reconcile with gateway statements
4. Contact support if needed

#### Regulator Access Denied
**Problem**: Access code not working
**Solution**:
1. Verify access code is valid
2. Check expiration time
3. Verify IP address is allowed
4. Check usage count limits

### Debug Mode

Enable debug logging:
```bash
export DEBUG=true
export LOG_LEVEL=DEBUG
```

Debug endpoints:
```http
GET /api/v1/debug/health
GET /api/v1/debug/gateways
GET /api/v1/debug/transactions
```

### Monitoring

#### Health Checks
```http
GET /api/v1/health
```

Response:
```json
{
    "status": "healthy",
    "timestamp": "2025-06-07T12:00:00Z",
    "services": {
        "database": "healthy",
        "redis": "healthy",
        "payment_gateways": "healthy"
    },
    "version": "1.0.0"
}
```

#### Metrics
```http
GET /api/v1/metrics
```

Response:
```json
{
    "transactions": {
        "total": 1000000,
        "success_rate": 98.5,
        "average_amount": 50000
    },
    "gateways": {
        "flutterwave": {"success_rate": 99.2, "response_time": 1200},
        "paystack": {"success_rate": 98.8, "response_time": 800},
        "paypal": {"success_rate": 97.5, "response_time": 1500}
    }
}
```

## Support

### Contact Information
- **Technical Support**: support@afcon360.com
- **Compliance**: compliance@afcon360.com
- **Security**: security@afcon360.com
- **Documentation**: docs.afcon360.com

### Emergency Contacts
- **Production Issues**: +256-123-456-789
- **Security Incidents**: security@afcon360.com
- **Regulatory Inquiries**: compliance@afcon360.com

---

*Last Updated: June 7, 2025*
*Version: 1.0.0*
