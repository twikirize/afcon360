# AFCON360 Deployment Guide - Enhanced MFA/KYC System

## 🚀 Quick Deployment Steps

### 1. Environment Setup
```bash
# Copy environment template (DO NOT share your actual .env)
cp env.example .env.local

# Add your actual secrets to .env (keep this private!)
# Your existing .env file should work, just ensure these keys are present:
# - SECRET_KEY
# - ENCRYPTION_KEY  
# - MFA_ENCRYPTION_KEY
# - DATABASE_URL
# - REDIS_URL
```

### 2. Database Migration
```bash
# Apply the enhanced MFA/KYC migration
flask db upgrade

# Or if using Docker:
docker-compose exec app flask db upgrade
```

### 3. Install Dependencies
```bash
# Install required Python packages
pip install pyotp qrcode[pil] cryptography

# Or with Docker (already included):
docker-compose build
```

### 4. Start Services
```bash
# Development
python app.py

# Production with Docker
docker-compose up -d
```

## 🔧 Configuration Checklist

### Required Environment Variables
- ✅ `SECRET_KEY` - Flask secret key
- ✅ `ENCRYPTION_KEY` - Data encryption key  
- ✅ `MFA_ENCRYPTION_KEY` - MFA backup codes encryption
- ✅ `DATABASE_URL` - PostgreSQL connection
- ✅ `REDIS_URL` - Redis connection

### Optional Enhanced Settings
- `MFA_BACKUP_CODES_COUNT=10` - Number of backup codes
- `KYC_ENHANCED_RISK_ASSESSMENT=true` - Enable risk scoring
- `SESSION_TIMEOUT_MINUTES=30` - Session timeout
- `PASSWORD_MIN_LENGTH=12` - Password requirements

## 🧪 Testing the Enhanced System

### Test MFA Functionality
1. Login to your account
2. Visit `/mfa/setup` to enable MFA
3. Scan QR code with authenticator app
4. Verify 6-digit code
5. Test backup codes

### Test Enhanced KYC
1. Upload verification documents
2. Check risk assessment in KYC status
3. Verify expiry warnings work
4. Test tier-based limits

### Test Security Features
1. Verify password policy enforcement
2. Test session timeout and rotation
3. Check session integrity validation
4. Verify AML screening integration

## 📊 Monitoring & Verification

### Health Checks
```bash
# Check application health
curl http://localhost:5000/health

# Check database connection
docker-compose exec app python -c "from app.extensions import db; print('DB OK')"

# Check Redis connection  
docker-compose exec app python -c "import redis; r=redis.Redis(); print('Redis OK')"
```

### Monitoring Dashboard
- Grafana: http://localhost:3000
- Prometheus: http://localhost:9090
- App: http://localhost:5000

## 🔒 Security Verification

### MFA Security
- [ ] Backup codes are encrypted in database
- [ ] TOTP secrets are stored securely
- [ ] QR codes expire after setup
- [ ] Session requires MFA for financial ops

### KYC Security  
- [ ] Document uploads are validated
- [ ] Risk assessment triggers alerts
- [ ] Expiry warnings work correctly
- [ ] High-risk users flagged appropriately

### Session Security
- [ ] Sessions rotate every 15 minutes
- [ ] IP/User agent validation works
- [ ] Session timeout enforced
- [ ] Invalid sessions are cleared

## 🆘 Troubleshooting

### Common Issues

#### MFA Not Working
```bash
# Check MFA encryption key is set
echo $MFA_ENCRYPTION_KEY

# Verify pyotp is installed
pip list | grep pyotp
```

#### KYC Risk Assessment Not Running
```bash
# Check enhanced KYC setting
grep KYC_ENHANCED_RISK_ASSESSMENT .env

# Verify database migration applied
flask db current
```

#### Session Issues
```bash
# Check Redis connection
docker-compose exec redis redis-cli ping

# Verify session timeout setting
grep SESSION_TIMEOUT_MINUTES .env
```

## 📝 Post-Deployment Checklist

### Immediate (Day 1)
- [ ] All services running
- [ ] Database migration applied
- [ ] MFA setup working
- [ ] KYC uploads processing
- [ ] Basic user registration works

### First Week
- [ ] Monitor error logs
- [ ] Test MFA backup codes
- [ ] Verify KYC risk scoring
- [ ] Check session management
- [ ] Test password policy

### First Month
- [ ] Review security logs
- [ ] Optimize performance
- [ ] Update documentation
- [ ] Train support team
- [ ] Plan scaling

## 📞 Support

For issues with the enhanced MFA/KYC system:

1. Check this guide first
2. Review application logs
3. Verify environment variables
4. Test individual components
5. Contact development team

---

**Version**: 2.0 - Enhanced MFA/KYC System  
**Updated**: 2025-05-07  
**Status**: ✅ Production Ready
